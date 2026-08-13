@{
    RootModule = 'FlowerOSEmoji.psm1'
    ModuleVersion = '0.1.0'
    GUID = 'db296363-4385-4c1d-b51e-0f10e0e0e001'
    Author = 'FlowerOS'
    CompanyName = 'FlowerOS'
    Copyright = '(c) 2026 FlowerOS. Unicode emoji data belongs to Unicode, Inc.; see NOTICE.md.'
    Description = 'FlowerOS emoji lookup commands backed by the official Unicode emoji-test data.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @('Get-Emoji', 'Get-AllEmoji', 'Update-EmojiCache', 'Get-EmojiDataInfo')
    CmdletsToExport = @()
    VariablesToExport = '*'
    AliasesToExport = @()
    PrivateData = @{
        PSData = @{
            Tags = @('FlowerOS', 'Emoji', 'Unicode', 'TUI')
            ProjectUri = 'https://www.unicode.org/Public/emoji/latest/emoji-test.txt'
            LicenseUri = 'https://www.unicode.org/terms_of_use.html'
        }
    }
}
