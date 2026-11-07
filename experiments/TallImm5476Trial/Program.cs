// Evaluation-only TallComponents dynamic XFA XDP importer.
// No real applicant data; never updates or overwrites the official PDF.
using System.Security.Cryptography;
using TallComponents.PDF;
using TallComponents.PDF.Forms.Data;

if (args.Length != 3)
    throw new ArgumentException("Expected official.pdf fictional.xdp output.pdf");
string input = Path.GetFullPath(args[0]);
string xdp = Path.GetFullPath(args[1]);
string output = Path.GetFullPath(args[2]);
if (input == output || File.Exists(output))
    throw new InvalidOperationException("Original and existing output must remain unchanged");
byte[] original = File.ReadAllBytes(input);
const string pinned = "aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4";
if (original.Length > 12_582_912
    || Convert.ToHexString(SHA256.HashData(original)).ToLowerInvariant() != pinned)
    throw new InvalidOperationException("Government IMM5476 blank SHA-256 mismatch");
if (Path.GetFileName(xdp) is not ("fictional-scalar.xdp" or "fictional-rich.xdp"))
    throw new InvalidOperationException("Only controlled fictional test XDP permitted");
using var inFile = new FileStream(input, FileMode.Open, FileAccess.Read);
var document = new Document(inFile);
using (var xdpFile = new FileStream(xdp, FileMode.Open, FileAccess.Read))
{
    var xdpData = new XdpFormData(xdpFile);
    document.Import(xdpData);
}
using (var outFile = new FileStream(output, FileMode.CreateNew, FileAccess.Write))
{
    document.Write(outFile);
}
Console.WriteLine($"TallComponents generated evaluation PDF: {new FileInfo(output).Length} bytes");
