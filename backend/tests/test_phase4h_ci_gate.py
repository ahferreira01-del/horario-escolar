"""Regressões do gate de homologação real PostgreSQL."""
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('phase4h_gate', ROOT/'scripts/verify_ci_pg_fase4h.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def make_xml(path, skipped=None, missing=None):
    root = ET.Element('testsuite')
    for name in module.REQUIRED:
        if name == missing:
            continue
        c = ET.SubElement(root,'testcase',{'name':name})
        if name == skipped:
            ET.SubElement(c,'skipped',{'message':'sem PostgreSQL'})
    ET.ElementTree(root).write(path)


def test_ci_gate_rejects_skipped_and_missing(tmp_path):
    p=tmp_path/'results.xml'
    make_xml(p)
    module.verify(p)
    make_xml(p,skipped=module.REQUIRED[0])
    with pytest.raises(RuntimeError,match='ignorado'):
        module.verify(p)
    make_xml(p,missing=module.REQUIRED[-1])
    with pytest.raises(RuntimeError,match='ausente'):
        module.verify(p)
