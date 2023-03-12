from pathlib        import Path
from pftag          import  pftag
from pftag.__main__ import main
from pftag.pftag    import parser_setup, parser_JSONinterpret, parser_interpret
from argparse       import  ArgumentParser, Namespace
import              pudb
import              pytest

@pytest.fixture(params = ['literal', 'os'])
def IOcomparisons_setup(request) -> tuple[str, str]:
    input:str
    output:str
    match request.param:
        case 'literal':
            input   = r'Hello, %literal_echo|Mars_!'
            output  = r'Hello, Mars!'
        case 'os':
            input   = r'This os is %os'
            output  = r'This os is posix'
    return input, output

def test_main(mocker, IOcomparisons_setup) -> None:
    """
    Simulated test run of the app using CLI.
    """
    input:str           = IOcomparisons_setup[0]
    output:str          = IOcomparisons_setup[1]
    mock_print          = mocker.patch('builtins.print')
    main(['--tag', input])
    mock_print.assert_called_once_with(output)

def test_noCLIinit() -> dict:
    # Here we create a tagger without the CLI parser
    # and run a tag lookup on a passed string. For the
    # sake of expediency, the original test string is
    # not transportable, so a simplified version is provided
    # but the original kept for reference
    str_tagNonTransportable:str =  r'run-%timestamp_chrplc|:|-_-OS-%platform-%NAME_dcmname_-%literal_echo|Subject4,md5|5_.log'
    str_tag:str = r'run-%2023-03-12T17:17:40.997150-04:00_chrplc|:|-_-OS-Linux-%NAME_dcmname|Patient_-%literal_echo|Subject4,md5|5_.log'
    tagger:pftag.Pftag     = pftag.Pftag({})

    d_tag:dict             = tagger(str_tag)
    assert d_tag['result'] == "run-2023-03-12T17-17-40.997150-04-00-OS-Linux-ROSALES^ANDREW-37149.log"
