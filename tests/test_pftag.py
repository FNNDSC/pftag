from pathlib        import Path
from pftag          import pftag
from pftag.__main__ import main
from pftag.pftag    import parser_setup, parser_JSONinterpret, parser_interpret, timestamp_dt
from argparse       import  ArgumentParser, Namespace
import  os
os.environ['XDG_CONFIG_HOME'] = '/tmp'
import              pudb
import              pytest
from datetime       import datetime
import              time
from typing         import Any

@pytest.fixture(params = ['literal', 'os'])
def IOcomparisons_setup(request) -> tuple[str, str]:
    """
    Setup some straightforward inputs and expected output
    results

    Args:
        request (_type_): internal pytest request

    Returns:
        tuple[str, str]: for each tag, return the input and expected result
    """
    input:str
    output:str
    match request.param:
        case 'literal':
            input   = r'Hello, %literal_echo|Mars_!'
            output  = r'Hello, Mars!'
        case 'os':
            input   = r'This os is %os'
            output  = r'This os is posix'
    print(f'Testing {input} transformed to {output}')
    return input, output

def test_main(mocker, IOcomparisons_setup) -> None:
    """
    Simulated test run of the app using CLI.
    """
    print(f'Testing IO comparisons')
    input:str           = IOcomparisons_setup[0]
    output:str          = IOcomparisons_setup[1]
    mock_print:Any      = mocker.patch('builtins.print')
    main(['--tag', input])
    mock_print.assert_called_once_with(output)

def test_noCLIinit() -> None:
    """
    Test when initializing the tagger object with an empty dictionary,
    i.e. simulating the case where no CLI is interpreted.
    """
    # Here we create a tagger without the CLI parser
    # and run a tag lookup on a passed string. For the
    # sake of expediency, the original test string is
    # not transportable, so a simplified version is provided
    # but the original kept for reference
    print(f'Testing init with no CLI')
    str_tagNonTransportable:str =  r'run-%timestamp_chrplc|:|-_-OS-%platform-%NAME_dcmname_-%literal_echo|Subject4,md5|5_.log'
    str_tag:str = r'run-%2023-03-12T17:17:40.997150-04:00_chrplc|:|-_-OS-Linux-%NAME_dcmname|Patient_-%literal_echo|Subject4,md5|5_.log'
    tagger:pftag.Pftag     = pftag.Pftag({})

    d_tag:dict             = tagger(str_tag)
    assert d_tag['result'] == "run-2023-03-12T17-17-40.997150-04-00-OS-Linux-ROSALES^ANDREW-37149.log"

def test_noTags() -> dict:
    """
    Test the case when the input string has no tags. In
    that case the output result is exactly the input.

    Returns:
        dict: _description_
    """
    print(f'Testing with string with no tags')
    str_tag:str = r'http://192.168.1.200:22223/api/v1/object/collection/event'
    tagger:pftag.Pftag      = pftag.Pftag({})
    d_tag:dict              = tagger(str_tag)
    assert d_tag['result']  == str_tag

def test_timestamp_dt() -> None:
    """
    Get a %timestamp and assert return type is datetime.
    """
    print(f'Testing timestamp_dt return')
    str_tag:str = r'%timestamp'
    tagger:pftag.Pftag      = pftag.Pftag({})
    d_tag:dict              = tagger(str_tag)
    dt:datetime             = timestamp_dt(d_tag['result'])
    assert type(dt)         == datetime

def test_timestamp_diff() -> None:
    """
    Test a 1 second timestamp difference
    """
    print(f'Testing 1 second time delay/track')
    tagger:pftag.Pftag      = pftag.Pftag({})
    d_tag:dict              = tagger(r'%timestamp')
    t1:str                  = d_tag['result']
    time.sleep(1)
    d_tag                   = tagger(r'%timestamp')
    t2:str                  = d_tag['result']
    dt_t1:datetime          = timestamp_dt(t1)
    dt_t2:datetime          = timestamp_dt(t2)
    dt:float                = (dt_t2 - dt_t1).total_seconds()
    diff:int                = round(dt)
    assert diff == 1
