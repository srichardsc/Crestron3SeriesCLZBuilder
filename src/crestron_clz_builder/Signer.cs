using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography.X509Certificates;
using Mono.Cecil;

// x86 bridge around the installed Crestron toolchain. The official
// SIMPLSharpService.VerifyAssembly path is required: the compiler's generic
// signing method uses a certificate that SPlusCC rejects for SIMPL# libraries.
internal static class Signer
{
    private const string SandboxHash = "FEF3EC6A8B41FAAE853038E36BD694975614AB5FAE643DB761EEBB9AB5C69EA5";
    private const string OfficialSignerThumbprint = "258CCE9B7DA79C8D5C33431BDA2DD32CB64AEC7D";

    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 5 && string.Equals(args[0], "patch", StringComparison.OrdinalIgnoreCase))
            {
                Patch(args[1], args[2], args[3], args[4]);
                Console.WriteLine("metadata=patched");
                return 0;
            }
            if (args.Length == 8 && string.Equals(args[0], "sign", StringComparison.OrdinalIgnoreCase))
            {
                Sign(args[1], args[2], args[3], args[4], args[5], args[6], args[7]);
                return 0;
            }
            Console.Error.WriteLine("usage: Signer.exe patch <assembly> <Mono.Cecil.dll> <CustomAttributes.dll> <stable-mvid>");
            Console.Error.WriteLine("   or: Signer.exe sign <assembly> <CSharpCompiler.dll> <Services.dll> <Ionic.Zip.dll> <workDir> <Cresdb> <thumbprint>");
            return 2;
        }
        catch (Exception ex)
        {
            Exception current = ex;
            while (current.InnerException != null) current = current.InnerException;
            Console.Error.WriteLine(current.GetType().FullName + ": " + current.Message);
            return 1;
        }
    }

    private static void RegisterResolver(string compilerPath, string servicesPath, string ionicPath, string cecilPath)
    {
        string[] paths = new[] { compilerPath, servicesPath, ionicPath, cecilPath };
        AppDomain.CurrentDomain.AssemblyResolve += delegate(object sender, ResolveEventArgs eventArgs)
        {
            AssemblyName requested = new AssemblyName(eventArgs.Name);
            for (int index = 0; index < paths.Length; index++)
            {
                string candidate = paths[index];
                if (candidate == null || !File.Exists(candidate)) continue;
                if (string.Equals(Path.GetFileNameWithoutExtension(candidate), requested.Name, StringComparison.OrdinalIgnoreCase))
                    return Assembly.LoadFrom(candidate);
            }
            return null;
        };
    }

    private static void Patch(string assemblyPath, string cecilPath, string customAttributesPath, string mvidText)
    {
        if (!File.Exists(assemblyPath)) throw new FileNotFoundException("Assembly", assemblyPath);
        if (!File.Exists(cecilPath)) throw new FileNotFoundException("Mono.Cecil", cecilPath);
        if (!File.Exists(customAttributesPath)) throw new FileNotFoundException("SimplSharpCustomAttributesInterface", customAttributesPath);
        RegisterResolver(null, null, null, cecilPath);
        Assembly cecilAssembly = typeof(AssemblyDefinition).Assembly;
        Type assemblyDefinitionType = cecilAssembly.GetType("Mono.Cecil.AssemblyDefinition", true);
        MethodInfo readAssembly = assemblyDefinitionType.GetMethod("ReadAssembly", new[] { typeof(string) });
        AssemblyDefinition definition = (AssemblyDefinition)readAssembly.Invoke(null, new object[] { Path.GetFullPath(assemblyPath) });
        AssemblyDefinition sdk = (AssemblyDefinition)readAssembly.Invoke(null, new object[] { Path.GetFullPath(customAttributesPath) });
        TypeDefinition attributeType = sdk.MainModule.GetType("Crestron.SandboxCustomAttributes.AssemblyInfoAttribute");
        if (attributeType == null) throw new InvalidOperationException("Sandbox AssemblyInfoAttribute not found");

        MethodDefinition constructor = null;
        for (int index = 0; index < attributeType.Methods.Count; index++)
        {
            MethodDefinition candidate = attributeType.Methods[index];
            if (candidate.Name == ".ctor" && candidate.Parameters.Count == 1)
            {
                constructor = candidate;
                break;
            }
        }
        if (constructor == null) throw new InvalidOperationException("Sandbox AssemblyInfoAttribute(string) not found");

        for (int index = definition.CustomAttributes.Count - 1; index >= 0; index--)
        {
            if (definition.CustomAttributes[index].AttributeType.FullName == "Crestron.SandboxCustomAttributes.AssemblyInfoAttribute")
                definition.CustomAttributes.RemoveAt(index);
        }
        MethodReference constructorReference = definition.MainModule.Import(constructor);
        CustomAttribute customAttribute = new CustomAttribute(constructorReference);
        customAttribute.ConstructorArguments.Add(new CustomAttributeArgument(definition.MainModule.TypeSystem.String, SandboxHash));
        definition.CustomAttributes.Add(customAttribute);

        AssemblyNameReference desktopMscorlib = null;
        for (int index = 0; index < definition.MainModule.AssemblyReferences.Count; index++)
        {
            AssemblyNameReference reference = definition.MainModule.AssemblyReferences[index];
            if (reference.Name == "mscorlib" && reference.Version == new Version(2, 0, 0, 0))
            {
                desktopMscorlib = reference;
                break;
            }
        }
        if (desktopMscorlib == null)
        {
            desktopMscorlib = new AssemblyNameReference("mscorlib", new Version(2, 0, 0, 0));
            desktopMscorlib.PublicKeyToken = new byte[] { 0xb7, 0x7a, 0x5c, 0x56, 0x19, 0x34, 0xe0, 0x89 };
            definition.MainModule.AssemblyReferences.Add(desktopMscorlib);
        }
        desktopMscorlib.Culture = string.Empty;
        Guid mvid = new Guid(mvidText);
        definition.MainModule.Mvid = mvid;
        string implementationDetailsName = "<PrivateImplementationDetails>{" + mvid.ToString("D").ToUpperInvariant() + "}";
        for (int index = 0; index < definition.MainModule.Types.Count; index++)
        {
            TypeDefinition type = definition.MainModule.Types[index];
            if (type.Name.StartsWith("<PrivateImplementationDetails>", StringComparison.Ordinal))
                type.Name = implementationDetailsName;
        }
        string normalizedPath = Path.GetFullPath(assemblyPath);
        definition.Write(normalizedPath);
        NormalizePeTimestamp(normalizedPath);
    }

    private static void NormalizePeTimestamp(string assemblyPath)
    {
        byte[] image = File.ReadAllBytes(assemblyPath);
        if (image.Length < 0x40) throw new InvalidDataException("PE image is truncated");
        int peOffset = BitConverter.ToInt32(image, 0x3c);
        if (peOffset < 0 || peOffset + 12 > image.Length || image[peOffset] != (byte)'P' || image[peOffset + 1] != (byte)'E')
            throw new InvalidDataException("PE signature not found");
        image[peOffset + 8] = 0;
        image[peOffset + 9] = 0;
        image[peOffset + 10] = 0;
        image[peOffset + 11] = 0;
        File.WriteAllBytes(assemblyPath, image);
    }

    private static void Sign(string assemblyPath, string compilerPath, string servicesPath, string ionicPath, string workDirectory, string cresdbPath, string expectedThumbprint)
    {
        if (!File.Exists(assemblyPath)) throw new FileNotFoundException("Assembly", assemblyPath);
        if (!File.Exists(compilerPath)) throw new FileNotFoundException("CSharpCompiler", compilerPath);
        if (!File.Exists(servicesPath)) throw new FileNotFoundException("SIMPLSharp services", servicesPath);
        if (!File.Exists(ionicPath)) throw new FileNotFoundException("Ionic.Zip", ionicPath);
        RegisterResolver(compilerPath, servicesPath, ionicPath, null);
        Assembly.LoadFrom(servicesPath);
        Assembly compilerAssembly = Assembly.LoadFrom(compilerPath);
        Type helperType = compilerAssembly.GetType("CSharpCompiler.CLZManagementHelper", true);
        ConstructorInfo constructor = helperType.GetConstructor(new[] { typeof(string), typeof(string), typeof(bool), typeof(bool), typeof(bool) });
        if (constructor == null) throw new InvalidOperationException("CLZManagementHelper constructor not found");
        object helper = constructor.Invoke(new object[] { Path.GetFullPath(workDirectory), Path.GetFullPath(cresdbPath), false, false, false });
        FieldInfo serviceField = helperType.GetField("_simplSharpService", BindingFlags.Instance | BindingFlags.NonPublic);
        if (serviceField == null) throw new InvalidOperationException("CLZManagementHelper._simplSharpService not found");
        object service = serviceField.GetValue(helper);
        MethodInfo verifyAssembly = service.GetType().GetMethod("VerifyAssembly", new[] { typeof(string) });
        if (verifyAssembly == null) throw new InvalidOperationException("SIMPLSharpService.VerifyAssembly not found");
        bool verified = (bool)verifyAssembly.Invoke(service, new object[] { Path.GetFullPath(assemblyPath) });
        if (!verified) throw new InvalidOperationException("SIMPLSharpService.VerifyAssembly returned false");

        X509Certificate certificate = X509Certificate.CreateFromSignedFile(Path.GetFullPath(assemblyPath));
        string thumbprint = BitConverter.ToString(certificate.GetCertHash()).Replace("-", string.Empty).ToUpperInvariant();
        Console.WriteLine("signatureThumbprint=" + thumbprint);
        if (!string.Equals(thumbprint, expectedThumbprint.ToUpperInvariant(), StringComparison.Ordinal))
            throw new InvalidOperationException("Unexpected Crestron signer thumbprint: " + thumbprint);
        if (!string.Equals(thumbprint, OfficialSignerThumbprint, StringComparison.Ordinal))
            throw new InvalidOperationException("Built-in Crestron signer thumbprint changed: " + thumbprint);
        Console.WriteLine("signature=official-crestron");
    }
}
