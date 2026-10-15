import sys

# Frozen, sys.executable is this program, not Python: the DOCX layout renderer starts its Word
# process as `<exe> -m pdfstruct.render ...`, so that call is answered here.
if sys.argv[1:3] == ["-m", "pdfstruct.render"]:
    from pdfstruct.render import main as render_main

    sys.exit(render_main(sys.argv[3:]))

from pdfstruct.gui.app import main

sys.exit(main())
