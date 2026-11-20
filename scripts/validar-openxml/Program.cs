using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Spreadsheet;
using DocumentFormat.OpenXml.Validation;

// Ferramenta de desenvolvimento/CI. Não faz parte da aplicação Python.
if (args.Length == 0)
{
    Console.Error.WriteLine("Informe o modelo e/ou os relatórios XLSX a validar.");
    return 2;
}

var validator = new OpenXmlValidator(FileFormatVersions.Office2016) { MaxNumberOfErrors = 100 };
var falhou = false;
foreach (var caminho in args)
{
    using var documento = SpreadsheetDocument.Open(caminho, false);
    var erros = validator.Validate(documento).ToList();
    foreach (var erro in erros)
        Console.Error.WriteLine($"{caminho}: {erro.Part?.Uri} {erro.Path?.XPath}: {erro.Description}");
    Console.WriteLine($"{caminho}: {erros.Count} erro(s) Open XML.");
    falhou |= erros.Count != 0;

    // Controle negativo: o SDK precisa detectar a falha que escapava ao leitor ZIP/XML.
    var folha = (Worksheet)documento.WorkbookPart!.WorksheetParts.First().Worksheet.CloneNode(true);
    var margens = folha.GetFirstChild<PageMargins>()!;
    margens.InsertAfterSelf(margens.CloneNode(true));
    if (!validator.Validate(folha).Any())
        throw new InvalidOperationException("O validador não detectou margens duplicadas.");
    Console.WriteLine("Controle negativo aprovado: margens duplicadas são rejeitadas.");
}
return falhou ? 1 : 0;
