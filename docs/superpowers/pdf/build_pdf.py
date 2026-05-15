"""
研发费用加计扣除风险管理体系 - PDF 装订集生成脚本
依赖：reportlab + Python 标准库
输入：docs/superpowers/{specs,plans,deliverables}/
输出：docs/superpowers/pdf/研发费用加计扣除风险管理体系-装订集.pdf
"""

import os
import re
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    KeepTogether, Preformatted, ListFlowable, ListItem
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY

# ---------------- 字体注册 ----------------
FONT_DIR = "C:/Windows/Fonts"
pdfmetrics.registerFont(TTFont("SimSun", f"{FONT_DIR}/simsun.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("SimHei", f"{FONT_DIR}/simhei.ttf"))
pdfmetrics.registerFont(TTFont("SimKai", f"{FONT_DIR}/simkai.ttf"))
pdfmetrics.registerFont(TTFont("MSYahei", f"{FONT_DIR}/msyh.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("MSYaheiBd", f"{FONT_DIR}/msyhbd.ttc", subfontIndex=0))

# ---------------- 样式定义 ----------------
styles = getSampleStyleSheet()

style_cover_title = ParagraphStyle(
    "CoverTitle", parent=styles["Title"],
    fontName="MSYaheiBd", fontSize=32, leading=44,
    alignment=TA_CENTER, textColor=colors.HexColor("#1a3a6e"),
    spaceAfter=20,
)
style_cover_subtitle = ParagraphStyle(
    "CoverSubtitle", parent=styles["Normal"],
    fontName="MSYahei", fontSize=16, leading=24,
    alignment=TA_CENTER, textColor=colors.HexColor("#444444"),
    spaceAfter=12,
)
style_cover_meta = ParagraphStyle(
    "CoverMeta", parent=styles["Normal"],
    fontName="SimSun", fontSize=12, leading=20,
    alignment=TA_CENTER, textColor=colors.HexColor("#666666"),
)
style_section_title = ParagraphStyle(
    "SectionTitle", parent=styles["Title"],
    fontName="MSYaheiBd", fontSize=28, leading=40,
    alignment=TA_CENTER, textColor=colors.HexColor("#1a3a6e"),
    spaceBefore=120, spaceAfter=20,
)
style_section_subtitle = ParagraphStyle(
    "SectionSubtitle", parent=styles["Normal"],
    fontName="SimSun", fontSize=14, leading=22,
    alignment=TA_CENTER, textColor=colors.HexColor("#555555"),
    spaceAfter=40,
)
style_h1 = ParagraphStyle(
    "H1", parent=styles["Heading1"],
    fontName="MSYaheiBd", fontSize=20, leading=28,
    textColor=colors.HexColor("#1a3a6e"),
    spaceBefore=12, spaceAfter=10,
    borderPadding=0,
)
style_h2 = ParagraphStyle(
    "H2", parent=styles["Heading2"],
    fontName="MSYaheiBd", fontSize=16, leading=22,
    textColor=colors.HexColor("#2c5fa0"),
    spaceBefore=10, spaceAfter=8,
)
style_h3 = ParagraphStyle(
    "H3", parent=styles["Heading3"],
    fontName="MSYaheiBd", fontSize=13, leading=18,
    textColor=colors.HexColor("#444444"),
    spaceBefore=6, spaceAfter=4,
)
style_h4 = ParagraphStyle(
    "H4", parent=styles["Heading4"],
    fontName="MSYaheiBd", fontSize=11, leading=16,
    textColor=colors.HexColor("#555555"),
    spaceBefore=4, spaceAfter=3,
)
style_body = ParagraphStyle(
    "Body", parent=styles["Normal"],
    fontName="SimSun", fontSize=10, leading=16,
    alignment=TA_JUSTIFY, textColor=colors.HexColor("#222222"),
    spaceBefore=2, spaceAfter=4,
)
style_quote = ParagraphStyle(
    "Quote", parent=style_body,
    fontName="SimKai", fontSize=10, leading=16,
    leftIndent=20, rightIndent=10,
    textColor=colors.HexColor("#666666"),
    borderColor=colors.HexColor("#cccccc"),
    borderWidth=0, borderPadding=5,
    backColor=colors.HexColor("#f5f5f5"),
)
style_code = ParagraphStyle(
    "Code", parent=styles["Code"],
    fontName="Courier", fontSize=8, leading=12,
    leftIndent=10, rightIndent=10,
    textColor=colors.HexColor("#111111"),
    backColor=colors.HexColor("#f0f0f0"),
    borderPadding=4,
)
style_li = ParagraphStyle(
    "ListItem", parent=style_body,
    leftIndent=16, bulletIndent=4,
)
style_toc_h1 = ParagraphStyle(
    "TocH1", parent=styles["Normal"],
    fontName="MSYaheiBd", fontSize=12, leading=22,
    textColor=colors.HexColor("#1a3a6e"),
    leftIndent=0, spaceBefore=6, spaceAfter=2,
)
style_toc_h2 = ParagraphStyle(
    "TocH2", parent=styles["Normal"],
    fontName="SimSun", fontSize=10, leading=16,
    textColor=colors.HexColor("#333333"),
    leftIndent=18, spaceBefore=0, spaceAfter=0,
)

# ---------------- HTML escape ----------------
def esc(text):
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

# Inline markdown: **bold** *italic* `code`
def inline_md(text):
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r'<font name="MSYaheiBd">\1</font>', text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r'<i>\1</i>', text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    return text

# ---------------- 表格解析 ----------------
def parse_table(lines, start):
    """从 start 行开始解析 Markdown 表格，返回 (table_data, end_index)"""
    table_data = []
    i = start
    while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
        line = lines[i].strip()
        # 跳过对齐行（含 :---: 这种）
        if re.match(r"^\|[\s:|-]+\|$", line):
            i += 1
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        table_data.append(cells)
        i += 1
    return table_data, i

def make_table(data):
    if not data:
        return None
    # 表头加粗
    formatted = []
    for row_idx, row in enumerate(data):
        formatted_row = []
        for cell in row:
            style = style_body
            if row_idx == 0:
                style = ParagraphStyle("th", parent=style_body, fontName="MSYaheiBd",
                                     textColor=colors.white)
            formatted_row.append(Paragraph(inline_md(cell), style))
        formatted.append(formatted_row)

    col_count = max(len(r) for r in formatted)
    # 列宽自适应
    page_width = A4[0] - 4*cm
    col_widths = [page_width / col_count] * col_count

    t = Table(formatted, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2c5fa0")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "MSYaheiBd"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))
    return t

# ---------------- 代码块 ----------------
def make_code(lines):
    text = "\n".join(lines)
    # ReportLab Preformatted 不支持 CJK 字体名为 Courier - 用 SimSun 渲染等宽
    return Preformatted(text, style_code)

# ---------------- Markdown → flowables ----------------
def parse_markdown_to_flowables(md_text, file_label=""):
    """简化 Markdown 解析器"""
    flowables = []
    lines = md_text.split("\n")
    i = 0
    in_yaml = False
    in_code = False
    code_buf = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # YAML frontmatter 跳过
        if i == 0 and stripped == "---":
            in_yaml = True
            i += 1
            continue
        if in_yaml:
            if stripped == "---":
                in_yaml = False
            i += 1
            continue

        # 代码块
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_buf = []
            else:
                in_code = False
                flowables.append(make_code(code_buf))
                flowables.append(Spacer(1, 4))
            i += 1
            continue
        if in_code:
            code_buf.append(line.rstrip())
            i += 1
            continue

        # 水平分割
        if stripped in ("---", "***", "___") and not in_code:
            flowables.append(Spacer(1, 6))
            i += 1
            continue

        # 标题
        if stripped.startswith("# "):
            flowables.append(Paragraph(inline_md(stripped[2:]), style_h1))
            i += 1
            continue
        if stripped.startswith("## "):
            flowables.append(Paragraph(inline_md(stripped[3:]), style_h2))
            i += 1
            continue
        if stripped.startswith("### "):
            flowables.append(Paragraph(inline_md(stripped[4:]), style_h3))
            i += 1
            continue
        if stripped.startswith("#### "):
            flowables.append(Paragraph(inline_md(stripped[5:]), style_h4))
            i += 1
            continue

        # 表格
        if "|" in line and i+1 < len(lines) and re.match(r"^\|?[\s:|-]+\|?$", lines[i+1].strip()):
            data, new_i = parse_table(lines, i)
            t = make_table(data)
            if t:
                flowables.append(t)
                flowables.append(Spacer(1, 4))
            i = new_i
            continue
        # 表格（无对齐行的连续 | 形式）
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            data, new_i = parse_table(lines, i)
            t = make_table(data)
            if t:
                flowables.append(t)
                flowables.append(Spacer(1, 4))
            i = new_i
            continue

        # 列表
        if re.match(r"^[\-\*\+]\s", stripped):
            items = []
            while i < len(lines) and re.match(r"^[\-\*\+]\s", lines[i].strip()):
                txt = lines[i].strip()[2:]
                items.append(Paragraph(inline_md(txt), style_li))
                i += 1
            flowables.append(ListFlowable(
                [ListItem(p, leftIndent=10) for p in items],
                bulletType="bullet", start="•",
            ))
            flowables.append(Spacer(1, 2))
            continue

        # 有序列表
        if re.match(r"^\d+\.\s", stripped):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i].strip()):
                txt = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                items.append(Paragraph(inline_md(txt), style_li))
                i += 1
            flowables.append(ListFlowable(
                [ListItem(p, leftIndent=10) for p in items],
                bulletType="1", start=1,
            ))
            flowables.append(Spacer(1, 2))
            continue

        # 引用
        if stripped.startswith(">"):
            quotes = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quotes.append(lines[i].strip().lstrip(">").strip())
                i += 1
            flowables.append(Paragraph(inline_md(" ".join(quotes)), style_quote))
            flowables.append(Spacer(1, 4))
            continue

        # 空行
        if not stripped:
            i += 1
            continue

        # 普通段落（含可能跨行）
        para_lines = []
        while i < len(lines) and lines[i].strip() and not (
            lines[i].strip().startswith("#") or
            lines[i].strip().startswith("```") or
            lines[i].strip().startswith(">") or
            re.match(r"^[\-\*\+]\s", lines[i].strip()) or
            re.match(r"^\d+\.\s", lines[i].strip()) or
            (lines[i].strip().startswith("|") and lines[i].strip().endswith("|"))
        ):
            para_lines.append(lines[i].strip())
            i += 1
        if para_lines:
            text = " ".join(para_lines)
            flowables.append(Paragraph(inline_md(text), style_body))

    return flowables

# ---------------- 页眉页脚 ----------------
class PageNumCanvas:
    def __init__(self):
        self.page_count = 0

PAGE_COUNT = {"total": 0}
SECTION_TITLE = {"current": ""}

def page_decoration(canvas, doc):
    canvas.saveState()
    # 页脚：页码
    canvas.setFont("SimSun", 9)
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.drawCentredString(A4[0]/2, 1.2*cm, f"— {doc.page} —")
    # 页眉：当前章节
    if SECTION_TITLE["current"]:
        canvas.drawString(2*cm, A4[1] - 1.2*cm, SECTION_TITLE["current"])
        canvas.drawRightString(A4[0]-2*cm, A4[1] - 1.2*cm,
                              "研发费用加计扣除风险管理体系")
        canvas.setStrokeColor(colors.HexColor("#cccccc"))
        canvas.line(2*cm, A4[1] - 1.4*cm, A4[0]-2*cm, A4[1] - 1.4*cm)
    canvas.restoreState()

def cover_decoration(canvas, doc):
    # 封面页无页眉页脚装饰
    canvas.saveState()
    # 添加边框
    canvas.setStrokeColor(colors.HexColor("#1a3a6e"))
    canvas.setLineWidth(2)
    canvas.rect(1.5*cm, 1.5*cm, A4[0]-3*cm, A4[1]-3*cm)
    canvas.setLineWidth(0.5)
    canvas.rect(1.7*cm, 1.7*cm, A4[0]-3.4*cm, A4[1]-3.4*cm)
    canvas.restoreState()

# ---------------- 主流程 ----------------
def build_pdf():
    base = Path("c:/Users/Arthur/workspace/docs/superpowers")
    out_path = base / "pdf" / "研发费用加计扣除风险管理体系-装订集.pdf"

    # 收集文件
    structure = [
        ("封面", None),
        ("目录", None),
        ("第一部分 设计文档（spec）", [base / "specs" / "2026-05-14-rd-deduction-risk-system-design.md"]),
        ("第二部分 Phase 1 实施计划", [base / "plans" / "2026-05-14-rd-deduction-risk-system-phase1.md"]),
        ("第三部分 Phase 2 实施计划", [base / "plans" / "2026-12-10-rd-deduction-risk-system-phase2.md"]),
    ]

    milestones = [
        ("第四部分 M0 启动文件", "M0"),
        ("第五部分 M1 治理层制度", "M1"),
        ("第六部分 M2 判定层制度", "M2"),
        ("第七部分 M3 证据层制度", "M3"),
        ("第八部分 M4 接口与强制规则", "M4"),
        ("第九部分 M5 内控层制度", "M5"),
        ("第十部分 M6 Phase 1 复盘", "M6"),
        ("第十一部分 M7 委外 / 合作研发合同治理", "M7"),
        ("第十二部分 M8 其他相关费用 5% 限额管控", "M8"),
        ("第十三部分 M9 三套口径并行", "M9"),
        ("第十四部分 M10 年度专项自查", "M10"),
        ("第十五部分 M11 留存备查档案", "M11"),
        ("第十六部分 M12 首次汇算清缴", "M12"),
        ("第十七部分 应急预案 4 件套（机密）", "Contingency"),
    ]

    for title, ms in milestones:
        ms_dir = base / "deliverables" / ms
        if ms_dir.exists():
            files = sorted(ms_dir.glob("*.md"))
            structure.append((title, files))

    # 创建 PDF 文档
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        topMargin=2.5*cm, bottomMargin=2*cm,
        leftMargin=2*cm, rightMargin=2*cm,
        title="研发费用加计扣除风险管理体系搭建方案",
        author="加计扣除办公室",
    )

    story = []

    # ============ 封面 ============
    story.append(Spacer(1, 4*cm))
    story.append(Paragraph("研发费用加计扣除", style_cover_title))
    story.append(Paragraph("风险管理体系", style_cover_title))
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("· 完整搭建方案 ·", style_cover_subtitle))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("大型软件 / 互联网 / IT 企业适用", style_cover_subtitle))
    story.append(Spacer(1, 4*cm))

    cover_meta_table = Table([
        ["版本", "v2.3"],
        ["编制单位", "研发费用加计扣除办公室"],
        ["编制日期", "2026-05-14"],
        ["文档数量", "43 份业务文件 + 完整方案"],
        ["体系周期", "24 个月（M0 – M24）"],
        ["保密级别", "内部 / 部分机密"],
    ], colWidths=[4*cm, 8*cm])
    cover_meta_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "SimSun"),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("ALIGN", (0,0), (0,-1), "RIGHT"),
        ("ALIGN", (1,0), (1,-1), "LEFT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#666666")),
        ("TEXTCOLOR", (1,0), (1,-1), colors.HexColor("#222222")),
        ("FONTNAME", (1,0), (1,-1), "MSYaheiBd"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("LINEBELOW", (0,0), (-1,-2), 0.3, colors.HexColor("#dddddd")),
    ]))
    story.append(cover_meta_table)
    story.append(PageBreak())

    # ============ 目录 ============
    SECTION_TITLE["current"] = "目录"
    story.append(Paragraph("目 录", style_h1))
    story.append(Spacer(1, 0.5*cm))
    for title, files in structure:
        if title in ("封面", "目录"):
            continue
        story.append(Paragraph(title, style_toc_h1))
        if files:
            for f in files:
                # 文件名作为二级目录
                name = f.stem
                # 去掉前缀编号
                clean = re.sub(r"^\d+-", "", name)
                story.append(Paragraph(f"· {clean}", style_toc_h2))
    story.append(PageBreak())

    # ============ 内容 ============
    for title, files in structure:
        if title in ("封面", "目录"):
            continue

        # 章节扉页
        SECTION_TITLE["current"] = title
        story.append(Spacer(1, 6*cm))
        story.append(Paragraph(title, style_section_title))
        if files:
            story.append(Paragraph(f"共 {len(files)} 份文件", style_section_subtitle))
        story.append(PageBreak())

        # 章节内容
        if files:
            for f in files:
                if not f.exists():
                    continue
                clean_name = re.sub(r"^\d+-", "", f.stem)
                SECTION_TITLE["current"] = f"{title} / {clean_name}"
                try:
                    md = f.read_text(encoding="utf-8")
                    flowables = parse_markdown_to_flowables(md, clean_name)
                    story.extend(flowables)
                except Exception as e:
                    story.append(Paragraph(f"[文件读取错误: {f.name} - {e}]", style_body))
                story.append(PageBreak())

    # 构建
    print(f"Building PDF... ({len(story)} flowables)".encode("ascii", errors="replace").decode())
    doc.build(story, onFirstPage=cover_decoration, onLaterPages=page_decoration)
    size_kb = out_path.stat().st_size / 1024
    print(f"[OK] PDF generated: {out_path}".encode("ascii", errors="replace").decode())
    print(f"     Size: {size_kb:.1f} KB")
    return out_path

if __name__ == "__main__":
    build_pdf()
