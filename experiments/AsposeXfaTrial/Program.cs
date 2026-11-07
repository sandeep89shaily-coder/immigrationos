// Native XFA proof-of-concept only; never handles real applicant data.
// Tests an authentic fixed-SHA IMM 5476 against Aspose's documented .NET
// XFA indexer. Does not generate signatures or claim IRCC validation.
using System.Security.Cryptography;
using System.Text.Json;
using Aspose.Pdf;

var report = new Dictionary<string, object?>
{
    ["engine"] = "Aspose.PDF .NET 26.9.0 evaluation",
    ["status"] = "not_tested",
    ["adobe_reader_tested"] = false,
    ["ready_for_submission"] = false,
    ["fictional_data_only"] = true
};

const string pinned = "aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4";
var values = new Dictionary<string, (string Field, string Value)>
{
    ["applicant_family"] = ("IMM_5476[0].Page1[0].SectionA[0].familyName[0]", "Sharma"),
    ["applicant_given"] = ("IMM_5476[0].Page1[0].SectionA[0].givenName[0]", "Aarav"),
    ["representative_family"] = ("IMM_5476[0].Page1[0].SectionB[0].familyName[0]", "Kapoor"),
    ["representative_given"] = ("IMM_5476[0].Page1[0].SectionB[0].givenName[0]", "Anita"),
};
string? reportPath = args.Length >= 3 ? args[2] : null;
try
{
    if (args.Length != 3)
        throw new InvalidOperationException("Expected blank-pdf, new-output-pdf, report-json");
    string inputPath = Path.GetFullPath(args[0]);
    string outputPath = Path.GetFullPath(args[1]);
    if (string.Equals(inputPath, outputPath, StringComparison.OrdinalIgnoreCase)
        || File.Exists(outputPath))
        throw new InvalidOperationException("Never overwrite original or existing output");
    byte[] original = File.ReadAllBytes(inputPath);
    if (original.Length > 12_582_912
        || Convert.ToHexString(SHA256.HashData(original)).ToLowerInvariant() != pinned)
        throw new InvalidOperationException("Official blank PDF checksum mismatch");
    string[] names;
    using (var inspected = new Document(inputPath))
    {
        names = inspected.Form.XFA.FieldNames;
    }
    report["xfa_field_count"] = names.Length;
    var selected = new Dictionary<string, string>();
    foreach (var (key, source) in values)
    {
        string[] matches = names.Where(name => name == source.Field
                 || name.EndsWith("." + source.Field, StringComparison.Ordinal)).ToArray();
        if (matches.Length > 1)
            throw new InvalidOperationException("Ambiguous XFA field: " + key);
        if (matches.Length == 1)
            selected[key] = matches[0];
    }
    report["matched_fields"] = selected.Keys.OrderBy(k => k).ToArray();
    report["write_method"] = "Document.Save() incremental update";
    if (selected.Count == 0)
    {
        report["status"] = "no_matching_fields_in_evaluation";
    }
    else
    {
        // Never alter the original: copy first, then write ONLY the copy.
        File.Copy(inputPath, outputPath);
        using (var stream = new FileStream(outputPath, FileMode.Open,
                                           FileAccess.ReadWrite, FileShare.None))
        using (var document = new Document(stream))
        {
            foreach (var (key, vendorName) in selected)
                document.Form.XFA[vendorName] = values[key].Value;
            // Parameterless Save() is Aspose's documented incremental save.
            document.Save();
        }
        byte[] generated = File.ReadAllBytes(outputPath);
        bool prefixPreserved = generated.Length >= original.Length
            && generated.AsSpan(0, original.Length).SequenceEqual(original);
        report["original_signed_byte_prefix_preserved"] = prefixPreserved;
        report["output_sha256"] = Convert.ToHexString(
            SHA256.HashData(generated)).ToLowerInvariant();
        report["status"] = prefixPreserved
            ? "saved_incrementally_unvalidated"
            : "nonincremental_rewrite_rejected";
    }
}
catch (Exception exc)
{
    report["status"] = "vendor_exception";
    report["exception"] = exc.GetType().Name;
    report["message"] = exc.Message.Length > 350 ? exc.Message[..350] : exc.Message;
}
finally
{
    string result = JsonSerializer.Serialize(report, new JsonSerializerOptions
    {
        WriteIndented = true
    });
    Console.WriteLine(result);
    if (reportPath is not null)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(reportPath))!);
        File.WriteAllText(reportPath, result);
    }
}
return (string)report["status"]! == "saved_incrementally_unvalidated" ? 0 : 2;
