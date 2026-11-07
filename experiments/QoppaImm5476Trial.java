// Evaluation-only Qoppa jPDFFields XDP importer. No real applicant input.
// Exercises SDK-native radio setters: XFA 1 <=> AcroForm option/on-state 0.
import com.qoppa.pdfFields.PDFFields;
import com.qoppa.pdf.form.FormField;
import com.qoppa.pdf.form.RadioButtonGroupField;
import com.qoppa.pdf.form.TextField;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Set;

public final class QoppaImm5476Trial {
    private static final String APPROVED_SHA =
        "aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4";
    private static final String APPOINTMENT =
        "IMM_5476[0].Page1[0].RadioButtonList[0]";
    private static final String UNPAID =
        "IMM_5476[0].Page1[0].SectionB[0].question6[0].questionI[0].uncompensated[0]";
    private static final String PAID_CICC =
        "IMM_5476[0].Page1[0].SectionB[0].question6[0].questionII[0].compensated[0]";

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
        String xdpFile = xdp.getFileName().toString();
        if (!Set.of("fictional-scalar.xdp", "fictional-rich.xdp",
                    "fictional-appointing-paid-cicc.xdp").contains(xdpFile)) {
            throw new IllegalArgumentException("Only fixed fictional test inputs allowed");
        }
        PDFFields document = new PDFFields(input.toString(), null);
        try {
            boolean paidCicc = xdpFile.equals("fictional-appointing-paid-cicc.xdp");
            // CRITICAL: Disable source rich-text mode BEFORE XDP import.
            // Otherwise Qoppa converts plain surnames into XHTML strings
            // inside the XFA datasets, which Acrobat displays as literal XML.
            if (paidCicc) {
                disableRichSurname(document,
                    "IMM_5476[0].Page1[0].SectionA[0].familyName[0]");
                disableRichSurname(document,
                    "IMM_5476[0].Page1[0].SectionB[0].familyName[0]");
            }
            document.importXDP(xdp.toString());
            if (paidCicc) {
                setPlainSurname(document,
                    "IMM_5476[0].Page1[0].SectionA[0].familyName[0]", "Sharma");
                setPlainSurname(document,
                    "IMM_5476[0].Page1[0].SectionB[0].familyName[0]", "Kapoor");
                // XFA import alone does not switch the PDF radio appearances.
                // Use the vendor-supported radio-field API.
                selectFirstOption(document, APPOINTMENT);
                selectFirstOption(document, PAID_CICC);
                FormField unpaid = document.getField(UNPAID);
                if (!(unpaid instanceof RadioButtonGroupField)
                    || !((RadioButtonGroupField)unpaid).getValue().equals("Off")) {
                    throw new IllegalStateException("Unrelated unpaid group selected");
                }
            }
            document.saveDocument(output.toString());
            System.out.println("Qoppa fictional PDF saved: " + output.getFileName()
                + " bytes=" + Files.size(output) + " (unvalidated trial only)");
        } finally {
            document.close();
        }
    }

    private static void disableRichSurname(PDFFields document, String name)
            throws Exception {
        FormField generic = document.getField(name);
        if (!(generic instanceof TextField)) {
            throw new IllegalStateException("Observed surname is not text: " + name);
        }
        TextField field = (TextField)generic;
        if (!field.isRichText() || !field.getValue().isEmpty()) {
            throw new IllegalStateException("Expected an empty original rich surname");
        }
        field.setFieldFlags(field.getFieldFlags() & ~TextField.FF_RICHTEXT);
        if (field.isRichText()) {
            throw new IllegalStateException("Cannot disable surname rich-text mode");
        }
    }

    private static void setPlainSurname(
            PDFFields document, String name, String value) throws Exception {
        FormField generic = document.getField(name);
        if (!(generic instanceof TextField)) {
            throw new IllegalStateException("Surname widget type changed: " + name);
        }
        TextField field = (TextField)generic;
        if (field.isRichText()) {
            throw new IllegalStateException("Surname rich text was reenabled during import");
        }
        field.setValue(value);
        if (!value.equals(field.getValue()) || field.getRichValue() != null) {
            throw new IllegalStateException("Surname must contain plain text without XHTML");
        }
    }

    private static void selectFirstOption(PDFFields document, String name) throws Exception {
        FormField field = document.getField(name);
        if (!(field instanceof RadioButtonGroupField)) {
            throw new IllegalStateException("Missing official radio group: " + name);
        }
        RadioButtonGroupField radio = (RadioButtonGroupField)field;
        if (radio.getOnValues().isEmpty() || radio.getOptions().isEmpty()
            || !radio.getOnValues().get(0).equals("0")
            || !radio.getOptions().get(0).equals("1")
            || !radio.getValue().equals("Off")) {
            throw new IllegalStateException("Official radio options changed: " + name);
        }
        radio.setValue("0");
        if (!radio.getValue().equals("0") || !radio.getValueFromOptions().equals("1")) {
            throw new IllegalStateException("Radio field failed SDK roundtrip: " + name);
        }
    }
}
