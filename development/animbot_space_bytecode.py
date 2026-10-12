"""Static inventory of animBot 3.13 bytecode for Space Switcher compatibility work.

This never imports or executes animBot modules. It reads CPython 3.13 .pyc code
objects through marshal, emits disassembly and follows nested functions/classes.
Run with Python 3.13; implementation-specific bytecode is not portable.
"""

import argparse
import dis
import hashlib
import marshal
import pathlib
import types


def descendants(code, prefix=""):
    path = prefix + "/" + code.co_name
    yield path, code
    for child in code.co_consts:
        if isinstance(child, types.CodeType):
            yield from descendants(child, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=pathlib.Path)
    parser.add_argument("--find", default="", help="Case-insensitive code path/name/constant match")
    parser.add_argument("--path", default="", help="Exact code-object path (avoids overlapping matches)")
    parser.add_argument("--dis", action="store_true", help="Disassemble matching code objects")
    parser.add_argument("--start", type=int, default=0, help="Bytecode offset to start printing")
    parser.add_argument("--end", type=int, default=10**9, help="Bytecode offset to stop printing")
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args()
    raw = args.file.read_bytes()
    root = marshal.loads(raw[16:])
    if not isinstance(root, types.CodeType):
        raise ValueError("No Python code object found")
    print("sha256=%s size=%s magic=%s" %
          (hashlib.sha256(raw).hexdigest(), len(raw), raw[:4].hex()))
    matches = 0
    for path, code in descendants(root):
        if args.path and path != args.path:
            continue
        constants = [c for c in code.co_consts if isinstance(c, str)]
        haystack = " ".join([path] + list(code.co_names) + constants).lower()
        if args.find.lower() not in haystack:
            continue
        print("\n%s [line %s] names=%s" % (path, code.co_firstlineno, ",".join(code.co_names)))
        print("  strings=%s" % repr(constants[:25]))
        if args.dis:
            for instruction in dis.get_instructions(code):
                if args.start <= instruction.offset < args.end:
                    print("  %5s  %-28s %s" %
                          (instruction.offset, instruction.opname, instruction.argrepr))
        matches += 1
        if matches >= args.limit:
            break
    print("\nmatched=%s" % matches)


if __name__ == "__main__":
    main()
