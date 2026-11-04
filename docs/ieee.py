"""Utilidades para generar documentos .docx con formato IEEE (dos columnas, Times New Roman 10 pt)."""
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

FUENTE = "Times New Roman"
ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV"]
LETRAS = "ABCDEFGHIJKLMNOP"
ANCHO_COL = 3.5


def _fuente(run, size=10, bold=False, italic=False, small_caps=False):
    run.font.name = FUENTE
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FUENTE)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.small_caps = small_caps
    return run


def _columnas(section, n, espacio_in=0.25):
    sectPr = section._sectPr
    cols = sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        sectPr.append(cols)
    cols.set(qn("w:num"), str(n))
    cols.set(qn("w:space"), str(int(espacio_in * 1440)))


class DocIEEE:
    def __init__(self):
        self.doc = Document()
        st = self.doc.styles["Normal"]
        st.font.name = FUENTE
        st.element.rPr.rFonts.set(qn("w:eastAsia"), FUENTE)
        st.font.size = Pt(10)
        pf = st.paragraph_format
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.line_spacing = 1.0
        s = self.doc.sections[0]
        s.page_width, s.page_height = Inches(8.5), Inches(11)
        s.top_margin, s.bottom_margin = Inches(0.75), Inches(1.0)
        s.left_margin = s.right_margin = Inches(0.625)
        _columnas(s, 1)
        self.n_sec = 0
        self.n_sub = 0
        self.n_fig = 0
        self.n_tab = 0
        self.n_eq = 0

    # ---------------------------------------------------------------- encabezado (una columna)
    def titulo(self, texto, autores, afiliacion, correo=""):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(10)
        _fuente(p.add_run(texto), 22)
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _fuente(p.add_run(autores), 11)
        for linea in afiliacion:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _fuente(p.add_run(linea), 10, italic=True)
        if correo:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _fuente(p.add_run(correo), 9)
        p.paragraph_format.space_after = Pt(12)
        # el resto del documento en dos columnas
        sec = self.doc.add_section(WD_SECTION.CONTINUOUS)
        _columnas(sec, 2)

    def resumen(self, texto, terminos):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _fuente(p.add_run("Resumen—"), 9, bold=True, italic=True)
        _fuente(p.add_run(texto), 9, bold=True)
        p.paragraph_format.space_after = Pt(6)
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _fuente(p.add_run("Términos de indexación—"), 9, bold=True, italic=True)
        _fuente(p.add_run(terminos), 9, bold=True)
        p.paragraph_format.space_after = Pt(4)

    # ---------------------------------------------------------------- texto
    def seccion(self, texto):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        _fuente(p.add_run(f"{ROMANOS[self.n_sec]}. {texto.upper()}"), 10, small_caps=True)
        self.n_sec += 1
        self.n_sub = 0

    def subseccion(self, texto):
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        _fuente(p.add_run(f"{LETRAS[self.n_sub]}. {texto}"), 10, italic=True)
        self.n_sub += 1

    def parrafo(self, *partes, sangria=True):
        """partes: str o tuplas (texto, 'b'|'i'|'bi'|'c')  (c = codigo)."""
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if sangria:
            p.paragraph_format.first_line_indent = Inches(0.17)
        for parte in partes:
            if isinstance(parte, tuple):
                t, f = parte
                r = p.add_run(t)
                if f == "c":
                    r.font.name = "Courier New"
                    r.font.size = Pt(8.5)
                else:
                    _fuente(r, 10, bold="b" in f, italic="i" in f)
            else:
                _fuente(p.add_run(parte), 10)
        return p

    def vinetas(self, items):
        for it in items:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.first_line_indent = Inches(-0.13)
            if isinstance(it, tuple):
                _fuente(p.add_run("• "), 10)
                _fuente(p.add_run(it[0]), 10, italic=True)
                _fuente(p.add_run(it[1]), 10)
            else:
                _fuente(p.add_run("• " + it), 10)

    def ecuacion(self, texto):
        self.n_eq += 1
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(3)
        ts = p.paragraph_format.tab_stops
        ts.add_tab_stop(Inches(ANCHO_COL / 2), WD_TAB_ALIGNMENT.CENTER)
        ts.add_tab_stop(Inches(ANCHO_COL), WD_TAB_ALIGNMENT.RIGHT)
        _fuente(p.add_run("\t" + texto), 10, italic=True)
        _fuente(p.add_run(f"\t({self.n_eq})"), 10)
        return self.n_eq

    # ---------------------------------------------------------------- figuras y tablas
    def figura(self, ruta, leyenda, ancho=ANCHO_COL - 0.05):
        self.n_fig += 1
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(str(ruta), width=Inches(ancho))
        c = self.doc.add_paragraph()
        c.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        c.paragraph_format.space_before = Pt(3)
        c.paragraph_format.space_after = Pt(8)
        _fuente(c.add_run(f"Fig. {self.n_fig}. "), 8)
        _fuente(c.add_run(leyenda), 8)
        return self.n_fig

    def tabla(self, titulo, encabezados, filas, anchos):
        self.n_tab += 1
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.keep_with_next = True
        _fuente(p.add_run(f"TABLA {ROMANOS[self.n_tab - 1]}"), 8)
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.keep_with_next = True
        _fuente(p.add_run(titulo.upper()), 8, small_caps=True)
        t = self.doc.add_table(rows=1, cols=len(encabezados))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        self._bordes(t)
        for i, h in enumerate(encabezados):
            self._celda(t.rows[0].cells[i], h, anchos[i], bold=True, fondo="E6E6E6")
        for fila in filas:
            cells = t.add_row().cells
            for i, v in enumerate(fila):
                self._celda(cells[i], v, anchos[i])
        sp = self.doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(6)
        return self.n_tab

    @staticmethod
    def _celda(cell, texto, ancho, bold=False, fondo=None):
        cell.width = Inches(ancho)
        tcPr = cell._tc.get_or_add_tcPr()
        if fondo:
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), fondo)
            tcPr.append(shd)
        mar = OxmlElement("w:tcMar")
        for lado in ("left", "right"):
            e = OxmlElement(f"w:{lado}")
            e.set(qn("w:w"), "50")
            e.set(qn("w:type"), "dxa")
            mar.append(e)
        tcPr.append(mar)
        p = cell.paragraphs[0]
        p.paragraph_format.first_line_indent = Inches(0)
        _fuente(p.add_run(texto), 7.5, bold=bold)

    @staticmethod
    def _bordes(t):
        tblPr = t._tbl.tblPr
        b = OxmlElement("w:tblBorders")
        for lado in ("top", "bottom", "insideH"):
            e = OxmlElement(f"w:{lado}")
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), "4")
            e.set(qn("w:color"), "000000")
            b.append(e)
        tblPr.append(b)

    # ---------------------------------------------------------------- referencias
    def referencias(self, refs):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        _fuente(p.add_run("REFERENCIAS"), 10, small_caps=True)
        for i, r in enumerate(refs, 1):
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.left_indent = Inches(0.3)
            p.paragraph_format.first_line_indent = Inches(-0.3)
            p.paragraph_format.tab_stops.add_tab_stop(Inches(0.3))
            _fuente(p.add_run(f"[{i}]\t{r}"), 8)

    def nota_pie_primera(self, texto):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(6)
        r = _fuente(p.add_run(texto), 8)
        r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    def guardar(self, ruta):
        self.doc.save(str(ruta))
