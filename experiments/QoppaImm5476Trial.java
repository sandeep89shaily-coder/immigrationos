// Evaluation-only Qoppa jPDFFields XDP importer. No real applicant input.
import com.qoppa.pdfFields.PDFFields;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class QoppaImm5476Trial {
    private static final String APPROVED_SHA =
        "aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4";

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println("usage: QoppaImm5476Trial official.pdf fictional.xdp output.pdf");
            System.exit(2);
        }
        Path input = Path.of(args[0]).toAbsolutePath().normalize();
        Path xdp = Path.of(args[1]).toAbsolutePath().normalize();
        Path output = Path.of(args[2]).toAbsolutePath().normalize();
        if (input.equals(output) || Files.exists(output)) {
            throw new IllegalArgumentException("Never overwrite government blank or existing output");
        }
        byte[] original = Files.readAllBytes(input);
        if (original.length > 12 * 1024 * 1024
                || !HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                         .digest(original)).equals(APPROVED_SHA)) {
            throw new IllegalArgumentException("Authentic IMM5476 SHA-256 mismatch");
        }
        if (!xdp.getFileName().toString().equals("fictional-scalar.xdp")
                && !xdp.getFileName().toString().equals("fictional-rich.xdp")) {
            throw new IllegalArgumentException("Only fixed fictional test inputs allowed");
        }
        PDFFields document = new PDFFields(input.toString(), null);
        document.importXDP(xdp.toString());
        document.saveDocument(output.toString());
        System.out.println("Qoppa output saved: " + output.getFileName()
            + " bytes=" + Files.size(output) + " (unvalidated, trial only)");
    }
}
