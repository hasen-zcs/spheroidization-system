# -*- coding: utf-8 -*-
"""生成《AI球化检测系统用户培训手册》docx（基于 frontend 实际页面编写，内嵌真实截图）。"""
import os

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = r"D:\项目组学习\项目工作\东贝生产线\系统架构\1.2\球化监测系统 (1)\spheroidization-system"
SHOT = os.path.join(ROOT, "manual-work")
OUT = os.path.join(ROOT, "docx", "AI球化检测系统用户培训手册（详细版）.docx")

FONT = "微软雅黑"
BLUE = RGBColor(0x00, 0x33, 0x99)      # 系统主色
BLUE2 = RGBColor(0x00, 0x50, 0xB3)
GREY = RGBColor(0x77, 0x77, 0x77)
DARK = RGBColor(0x1A, 0x2A, 0x3A)
RED = RGBColor(0xC6, 0x28, 0x28)
GREEN = RGBColor(0x16, 0x80, 0x3C)
ORANGE = RGBColor(0xD9, 0x77, 0x06)


def set_cjk(rpr, name=FONT):
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.insert(0, rf)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia"):
        rf.set(qn(attr), name)


def style_run(run, size=10.5, bold=False, color=None, name=FONT):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    set_cjk(run._element.get_or_add_rPr(), name)


def add_para(doc, text="", size=10.5, bold=False, color=None, align=None,
             space_before=0, space_after=6, indent=None, line=1.35):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing = line
    if align is not None:
        p.alignment = align
    if indent is not None:
        pf.left_indent = Cm(indent)
    if text:
        style_run(p.add_run(text), size=size, bold=bold, color=color)
    return p


def add_rich(doc, parts, align=None, space_after=6, indent=None, line=1.35):
    """parts: list of (text, kwargs) tuples in one paragraph."""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.line_spacing = line
    if align is not None:
        p.alignment = align
    if indent is not None:
        pf.left_indent = Cm(indent)
    for text, kw in parts:
        style_run(p.add_run(text), **kw)
    return p


def add_heading(doc, text, level=1):
    p = doc.add_heading(level=level)
    sizes = {1: 16, 2: 13, 3: 11.5}
    colors = {1: BLUE, 2: BLUE2, 3: DARK}
    run = p.add_run(text)
    style_run(run, size=sizes.get(level, 12), bold=True, color=colors.get(level, DARK))
    pf = p.paragraph_format
    pf.space_before = Pt(16 if level == 1 else 10)
    pf.space_after = Pt(8 if level == 1 else 6)
    return p


def add_bullet(doc, text, bold_prefix=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(3)
    pf.line_spacing = 1.3
    pf.left_indent = Cm(0.5)
    style_run(p.add_run("• "), size=10.5, color=BLUE2)
    if bold_prefix:
        style_run(p.add_run(bold_prefix), size=10.5, bold=True)
    style_run(p.add_run(text), size=10.5)
    return p


def add_step(doc, num, text, note=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(4)
    pf.line_spacing = 1.35
    pf.left_indent = Cm(0.3)
    style_run(p.add_run("第 %d 步　" % num), size=10.5, bold=True, color=BLUE)
    style_run(p.add_run(text), size=10.5)
    if note:
        style_run(p.add_run("（" + note + "）"), size=9.5, color=GREY)
    return p


def shade_cell(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def cell_text(cell, text, bold=False, size=10, color=None, align=None, fill=None):
    cell.text = ""
    p = cell.paragraphs[0]
    pf = p.paragraph_format
    pf.space_after = Pt(2)
    pf.space_before = Pt(2)
    pf.line_spacing = 1.25
    if align is not None:
        p.alignment = align
    style_run(p.add_run(text), size=size, bold=bold, color=color)
    if fill:
        shade_cell(cell, fill)


def add_table(doc, headers, rows, widths=None, header_fill="003399",
              zebra=True, font_size=10, first_col_bold=False):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for i, h in enumerate(headers):
        cell_text(table.rows[0].cells[i], h, bold=True, size=font_size,
                  color=RGBColor(0xFF, 0xFF, 0xFF),
                  align=WD_ALIGN_PARAGRAPH.CENTER, fill=header_fill)
    for r, row in enumerate(rows):
        cells = table.add_row().cells
        fill = "F2F7FC" if (zebra and r % 2 == 1) else None
        for i, val in enumerate(row):
            cell_text(cells[i], str(val), size=font_size,
                      bold=(first_col_bold and i == 0), fill=fill)
    if widths:
        for i, w in enumerate(widths):
            for row in table.rows:
                row.cells[i].width = Cm(w)
    return table


def add_figure(doc, shot_file, caption, width_cm=15.4):
    path = os.path.join(SHOT, shot_file)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run()
    run.add_picture(path, width=Cm(width_cm))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(10)
    style_run(cap.add_run(caption), size=9, color=GREY)


def add_tip(doc, title, text, fill="EFF6FF", bar_color=BLUE):
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    cell = table.rows[0].cells[0]
    cell.width = Cm(15.4)
    shade_cell(cell, fill)
    cell.text = ""
    p1 = cell.paragraphs[0]
    p1.paragraph_format.space_before = Pt(4)
    p1.paragraph_format.space_after = Pt(2)
    style_run(p1.add_run(title + "："), size=10, bold=True, color=bar_color)
    style_run(p1.add_run(text), size=10)
    add_para(doc, "", size=4, space_after=2)


def add_page_number(paragraph):
    run = paragraph.add_run()
    f1 = OxmlElement("w:fldChar")
    f1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = "PAGE"
    f2 = OxmlElement("w:fldChar")
    f2.set(qn("w:fldCharType"), "end")
    run._r.append(f1)
    run._r.append(it)
    run._r.append(f2)
    style_run(run, size=9, color=GREY)


def clean_doc_props(path):
    """清除文档属性中的自动生成痕迹（作者、备注、模板来源与模板日期）。"""
    import re
    import zipfile
    from datetime import datetime

    now = datetime.now().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    tmp = path + ".tmp"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/core.xml":
                text = data.decode("utf-8")
                text = text.replace("<dc:creator>python-docx</dc:creator>", "<dc:creator/>")
                text = text.replace("<dc:description>generated by python-docx</dc:description>",
                                    "<dc:description/>")
                text = re.sub(r"(<dcterms:created[^>]*>)[^<]*(</dcterms:created>)",
                              r"\g<1>" + now + r"\g<2>", text)
                text = re.sub(r"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                              r"\g<1>" + now + r"\g<2>", text)
                data = text.encode("utf-8")
            elif item.filename == "docProps/app.xml":
                data = data.decode("utf-8").replace(
                    "Microsoft Macintosh Word", "Microsoft Office Word").encode("utf-8")
            zout.writestr(item, data)
    os.replace(tmp, path)


# ============================== 文档 ==============================

doc = Document()

# 页面：A4
sec = doc.sections[0]
sec.page_width = Cm(21.0)
sec.page_height = Cm(29.7)
sec.left_margin = Cm(2.2)
sec.right_margin = Cm(2.2)
sec.top_margin = Cm(2.0)
sec.bottom_margin = Cm(2.0)

# Normal 样式
normal = doc.styles["Normal"]
normal.font.name = FONT
normal.font.size = Pt(10.5)
set_cjk(normal._element.get_or_add_rPr())

# 页脚：标题 + 页码
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
style_run(fp.add_run("AI球化检测系统用户培训手册（详细版）　·　第 "), size=9, color=GREY)
add_page_number(fp)
style_run(fp.add_run(" 页"), size=9, color=GREY)

# ---------------- 封面 ----------------
for _ in range(5):
    add_para(doc, "", space_after=12)
add_para(doc, "AI球化检测系统", size=30, bold=True, color=BLUE,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8)
add_para(doc, "用 户 培 训 手 册", size=20, bold=True, color=DARK,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=18)
add_para(doc, "浇注工位 AI 智能化 · 球化检测记录管理", size=12, color=GREY,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=60)

info = doc.add_table(rows=5, cols=2)
info.style = "Table Grid"
info.alignment = WD_TABLE_ALIGNMENT.CENTER
info_rows = [("文档版本", "V2.0（详细版 · 供项目存档）"),
             ("适用对象", "浇注工位操作人员、工艺/质量技术人员、班组长、项目存档"),
             ("配套文档", "《AI球化检测系统用户培训手册（精简版）》——供一线操作工日常操作快速查阅"),
             ("编制依据", "系统当前前端版本（2026 年 10 月）"),
             ("截图说明", "截图均为系统实际运行画面（2026 年 10 月 8 日截取）")]
for i, (k, v) in enumerate(info_rows):
    cell_text(info.rows[i].cells[0], k, bold=True, size=10.5,
              align=WD_ALIGN_PARAGRAPH.CENTER, fill="E6F2FF")
    cell_text(info.rows[i].cells[1], v, size=10.5)
    info.rows[i].cells[0].width = Cm(3.6)
    info.rows[i].cells[1].width = Cm(10.0)
add_para(doc, "", space_after=16)
add_para(doc, "东贝生产线 · 系统架构项目组", size=11, color=GREY,
         align=WD_ALIGN_PARAGRAPH.CENTER)
doc.add_page_break()

# ---------------- 目录（静态） ----------------
add_heading(doc, "目录", 1)
toc = [
    "1　系统简介",
    "2　认识系统界面",
    "3　浇注工位监控（系统首页）",
    "4　首页：统计概览",
    "5　球化记录：查询与管理",
    "6　异常记录",
    "7　球化记录详情：复核与处理",
    "8　检测标准管理",
    "9　常用业务流程",
    "10　常见问题（FAQ）",
    "11　附录：名词解释",
]
for line in toc:
    add_para(doc, line, size=11, space_after=8)
add_para(doc, "", space_after=4)
add_para(doc, "说明：本手册中的截图均来自系统实际运行画面，与当前版本界面一致。",
         size=9, color=GREY)
add_para(doc, "配套文档：《AI球化检测系统用户培训手册（精简版）》，供一线工人操作使用。",
         size=9, color=GREY)
doc.add_page_break()

# ---------------- 1 系统简介 ----------------
add_heading(doc, "1　系统简介", 1)

add_heading(doc, "1.1　这个系统是做什么的", 2)
add_para(doc,
         "AI球化检测系统是浇注工位的“数据管家”。上游的 AI 检测设备（检测模块）负责对每一包铁水的"
         "球化过程进行自动检测并产生结果，并自动推送到本系统；本系统负责把这些检测结果集中管理起来，"
         "操作人员通常无需手工录入数据。系统具体包括：")
for t, b in [
    ("球化检测记录管理", "每一次球化检测都会生成一条记录，包含时间、温度、重量、球化时长等数据；"),
    ("异常记录查询", "机器判定为“异常”的记录可以单独筛选出来，方便优先处理；"),
    ("人工复核", "对机器检测结果有异议时，由人工填写复核结论，与机器结果分开保存、互不覆盖；"),
    ("处理状态管理", "异常记录确认处置完成后，可以“标记为已处理”，并记录处理人和处理时间；"),
    ("检测标准管理", "维护球化时间标准、称重标准，支持历史版本保留与随时切换。"),
]:
    add_rich(doc, [
        ("• ", {"size": 10.5, "color": BLUE2}),
        (t + "：", {"size": 10.5, "bold": True}),
        (b, {"size": 10.5}),
    ], indent=0.5, space_after=3)
add_para(doc, "", space_after=2)
add_rich(doc, [
    ("简单理解：", {"size": 10.5, "bold": True, "color": BLUE}),
    ("机器负责“检”（检测结果自动推送进系统），系统负责“记、查、核、管”。"
     "操作工和工艺人员每天都在这个界面上工作。",
     {"size": 10.5}),
])
add_tip(doc, "重要：非必要不要新增",
        "检测记录正常由上游检测模块自动推送生成，不需要人工录入。"
        "系统提供的“新增记录”功能只用于特殊情况下的补录，请勿随意手工新增数据。",
        fill="FDECEC", bar_color=RED)

add_heading(doc, "1.2　谁能用", 2)
for t in [
    "浇注工位操作工：查看实时画面和最新检测数据（数据由检测模块自动推送，仅在确需补录时手工新增）；",
    "工艺/质量技术人员：复核异常记录、标记处理、调整检测标准；",
    "班组长/统计人员：在首页查看总记录数、异常数、已处理/未处理情况。",
]:
    add_bullet(doc, t)

add_heading(doc, "1.3　如何打开系统", 2)
add_step(doc, 1, "使用 Microsoft Edge 或 Google Chrome 浏览器（建议使用最新版）。")
add_step(doc, 2, "在浏览器地址栏输入系统地址并回车，例如测试环境为 http://localhost:5173 ，"
                 "正式环境以 IT 部门分发的地址为准。")
add_step(doc, 3, "页面打开后即进入“浇注工位监控”首页，无需登录即可使用。")
add_tip(doc, "提示", "建议将浏览器窗口最大化使用；屏幕分辨率 1366×768 及以上时显示效果最佳。"
       "页面右上角的“系统正常”按钮表示后端服务连接正常，可点击查看连接状态。")

# ---------------- 2 认识系统界面 ----------------
add_heading(doc, "2　认识系统界面", 1)
add_para(doc,
         "整个系统由一个顶部导航栏和两个大的功能区域组成。顶部导航栏在所有页面都存在，"
         "包含 3 个元素（从左到右）：")
add_table(doc,
          ["位置", "名称", "作用"],
          [
              ["左侧", "采集管理（系统标识）", "点击返回“浇注工位监控”首页"],
              ["中间", "浇注工位监控", "进入实时监控页（系统首页）"],
              ["中间", "异常记录", "直接进入异常记录页，只列出机器判异常的记录"],
              ["右侧", "系统状态按钮", "显示“系统正常 / 系统离线 / 连接中”，点击可重新检测连接"],
          ],
          widths=[2.2, 4.4, 8.8], first_col_bold=True)
add_para(doc, "", space_after=2)
add_para(doc,
         "进入“记录区”（首页 / 球化记录 / 异常记录 / 检测标准）后，页面变为“左侧功能菜单 + 右侧内容”的布局，"
         "左侧菜单共 4 项：")
add_table(doc,
          ["菜单项", "页面地址", "用途"],
          [
              ["首页", "/records/home", "统计数据总览 + 最近检测记录"],
              ["球化记录", "/records/spheroidization", "查询全部球化检测记录、新增记录"],
              ["异常记录", "/records/abnormal", "只查看机器判“异常”的记录并处理"],
              ["检测标准", "/records/standard", "查看/创建/应用检测标准"],
          ],
          widths=[3.2, 5.4, 6.8], first_col_bold=True)
add_tip(doc, "提示", "左侧菜单和顶部“异常记录”链接打开的是同一个异常页面，只是入口不同；"
       "从哪边进都行。")

# ---------------- 3 浇注工位监控 ----------------
add_heading(doc, "3　浇注工位监控（系统首页）", 1)
add_para(doc,
         "打开系统后首先看到的就是“浇注工位监控”页面（标题：浇注工位AI智能化系统）。"
         "这一页用于班中随时“瞄一眼”：两个摄像头的实时画面、最近 5 条检测数据、"
         "以及当前记录的状态。")
add_figure(doc, "01_monitor.png", "图 1　浇注工位监控页面（顶部导航栏、摄像头画面、最新检测数据与状态栏）")

add_heading(doc, "3.1　摄像头视频窗口", 2)
add_para(doc, "页面上方并排显示两个摄像头窗口：浇注工位 #01 和 浇注工位 #02。")
add_bullet(doc, "窗口右上角显示绿色“● 视频流”：摄像头在线，画面正常；", bold_prefix=None)
add_bullet(doc, "显示橙色“未连接”、窗口内为“等待视频流接入”：摄像头或视频服务未上线，画面接入后会自动显示。")
add_para(doc, "视频窗口本身只用于观看，不需要操作。")

add_heading(doc, "3.2　“新增一行数据”按钮（非必要不要用）", 2)
add_para(doc,
         "视频窗口下方的“＋ 新增一行数据”按钮，会跳转到“球化记录”页面并自动打开新增表单"
         "（详见第 5.3 节），用于手工补录一条检测数据。")
add_tip(doc, "重要：非必要不要新增",
        "检测记录正常由上游检测模块自动推送并写入系统，无需人工新增。该按钮仅在确有需要"
        "（如检测模块未能自动推送）时才使用；随意手工新增会产生重复记录，干扰统计结果与质量追溯。",
        fill="FDECEC", bar_color=RED)

add_heading(doc, "3.3　最新检测数据表", 2)
add_para(doc, "中间表格按检测时间从新到旧显示最近 5 条记录，各列含义如下：")
add_table(doc,
          ["列名", "含义"],
          [
              ["序号", "记录编号（ID），点击“异常记录”或详情页可用它找到对应记录"],
              ["球化重量", "本次检测对应铁水的重量"],
              ["测温时间 / 温度", "测温的时刻与铁水温度"],
              ["进线开始/结束时间", "进线开始与结束的时刻"],
              ["进线持续时间", "进线的总时长"],
              ["球化开始/结束时间", "球化反应开始与结束的时刻"],
              ["球化时间", "本次实际球化反应时长"],
              ["球化结果", "机器判定：正常 / 异常"],
              ["报警原因", "异常时显示原因（如“球化异常”），正常显示“无”"],
          ],
          widths=[4.6, 10.8])
add_para(doc, "", space_after=2)
add_rich(doc, [
    ("注意：", {"size": 10.5, "bold": True, "color": ORANGE}),
    ("个别列显示“--”，表示老记录没有这项数据，属于正常现象。", {"size": 10.5}),
])

add_heading(doc, "3.4　底部状态栏", 2)
add_para(doc, "页面最下方的蓝色信息栏显示“当前最新一条记录”的概况：")
add_table(doc,
          ["字段", "含义"],
          [
              ["当前记录状态", "最新记录是“待处理”还是“已处理”"],
              ["标准/实际球化时间", "格式为“标准值 / 实际值”，一眼对比是否达标"],
              ["检测时间", "最新记录的检测时刻"],
              ["检测结果", "机器判定：正常 / 异常"],
              ["处理人", "已处理时显示处理人姓名，未处理显示“--”"],
          ],
          widths=[4.6, 10.8])

# ---------------- 4 首页统计 ----------------
add_heading(doc, "4　首页：统计概览", 1)
add_para(doc,
         "在左侧菜单点击“首页”进入统计概览页。这一页回答三个问题："
         "“一共检了多少？”“有多少异常？”“处理得怎么样？”")
add_figure(doc, "02_home.png", "图 2　首页统计概览（统计卡片、最近检测记录、快捷操作）")

add_heading(doc, "4.1　统计卡片", 2)
add_table(doc,
          ["卡片", "含义"],
          [
              ["总记录数", "系统中球化检测记录的总数"],
              ["异常记录", "机器判定为“异常”的记录数（红色数字）"],
              ["已处理", "已标记为“已处理”的记录数（绿色数字）"],
              ["未处理", "尚未处理的记录数（橙色数字）"],
          ],
          widths=[4.6, 10.8])
add_para(doc, "右上角“刷新”按钮可重新拉取最新数据。")

add_heading(doc, "4.2　最近检测记录", 2)
add_para(doc,
         "表格显示最近 5 条记录（ID、检测时间、球化开始/结束时间、检测结果、处理状态）。"
         "点击行尾的“查看详情”进入该记录的详情页（第 7 章）；"
         "点击“查看全部”进入球化记录列表（第 5 章）。")

add_heading(doc, "4.3　快捷操作", 2)
add_para(doc,
         "页面底部的两个按钮“查看球化记录”“管理检测标准”分别是第 5 章和第 8 章页面的快捷入口。")

# ---------------- 5 球化记录 ----------------
add_heading(doc, "5　球化记录：查询与管理", 1)
add_para(doc,
         "“球化记录”页面是记录的主列表：所有检测记录都在这里查询、翻页；"
         "确需补录时才使用“新增记录”（见第 5.3 节）。")
add_figure(doc, "03_records.png", "图 3　球化记录列表（查询条件、记录表格、分页）")

add_heading(doc, "5.1　查询记录", 2)
add_step(doc, 1, "在“检测结果”下拉框选择：全部 / 正常 / 异常。")
add_step(doc, 2, "在“处理状态”下拉框选择：全部 / 已处理 / 未处理。")
add_step(doc, 3, "点击“查询”按钮，表格显示符合条件的记录（每页 20 条）。")
add_para(doc, "右上角“刷新”按钮用于重新加载当前列表。")

add_heading(doc, "5.2　记录列表各列含义", 2)
add_table(doc,
          ["列名", "含义"],
          [
              ["ID", "记录编号"],
              ["检测时间", "检测发生的时刻"],
              ["铁水重量 / 铁水温度", "本次检测的重量与温度"],
              ["球化开始/结束时间", "球化反应起止时刻"],
              ["进线开始/结束时间", "进线起止时刻"],
              ["标准/实际球化时长", "“标准值 / 实际值”，判断是否达标的关键列"],
              ["实际进线时间", "进线总时长"],
              ["检测结果", "机器判定：正常 / 异常"],
              ["复核状态", "最近一次人工复核的结论；为空表示还没有人复核过"],
              ["处理状态", "未处理（橙色）/ 已处理（绿色）"],
              ["操作", "“查看详情”进入详情页"],
          ],
          widths=[4.6, 10.8])
add_para(doc, "列表底部有分页：上一页 / 第 X / Y 页，共 N 条 / 下一页。")

add_heading(doc, "5.3　新增球化记录（仅用于特殊情况补录）", 2)
add_tip(doc, "重要：非必要不要新增",
        "系统的球化检测记录正常由上游检测模块自动推送生成，操作人员一般不需要手工新增，"
        "“新增记录”只用于检测模块未自动推送、确需补录的特殊情况。"
        "随意新增会形成重复记录，影响统计准确性和质量追溯；补录前请先确认该记录确实不存在，"
        "并填写真实完整的检测数据。",
        fill="FDECEC", bar_color=RED)
add_para(doc, "点击右上角“新增记录”按钮，会展开一张“新增球化记录”表单（见图 4）。")
add_figure(doc, "04_records_create.png", "图 4　新增球化记录表单（各输入项、机器判定异常勾选、球化图片选择）")
add_table(doc,
          ["字段", "说明"],
          [
              ["检测时间", "本次检测发生的日期时间，如 2026-09-06 18:00:00"],
              ["球化开始时间 / 结束时间", "球化反应起止时刻"],
              ["实际球化时间", "本次实际球化反应时长（秒）"],
              ["球化温度 / 测温时间", "铁水温度（℃）及测温时刻"],
              ["进线开始/结束时间", "进线起止时刻"],
              ["进线总时长", "进线总时长（秒）"],
              ["球化重量", "铁水重量"],
              ["机器判定异常", "若机器判定为异常，勾选此项"],
              ["球化图片（JPG）", "点“选择 JPG 文件”上传检测图片，选中后可预览、可“清除图片”"],
          ],
          widths=[5.0, 10.4])
add_para(doc, "填写完成后点击“提交记录”。新记录会立即出现在列表第一页，"
              "并自动保存创建时生效的检测标准快照（标准快照机制见第 8 章）。")
add_tip(doc, "注意", "球化图片只支持 JPG 格式，选择其他格式会提示“请选择有效的 JPG 图片”。"
       "“机器判定异常”勾选后，该记录会出现在“异常记录”页面。")

# ---------------- 6 异常记录 ----------------
add_heading(doc, "6　异常记录", 1)
add_para(doc,
         "“异常记录”页面与“球化记录”页面布局相同，区别是：它自动只筛选出"
         "机器判定为“异常”的记录（“检测结果”条件固定为“异常”，不可修改）。")
add_figure(doc, "05_abnormal.png", "图 5　异常记录页面（自动只列出异常记录）")
add_para(doc, "日常处理异常的标准动作：")
add_step(doc, 1, "进入“异常记录”页面，找到“未处理”的异常记录。")
add_step(doc, 2, "点击“查看详情”，查看球化亮光分析曲线和机器检测结果（第 7 章）。")
add_step(doc, 3, "需要人工确认时填写“人工复核”（复核结论、复核人、复核说明）。")
add_step(doc, 4, "确认处置完成后填写处理人，点击“标记为已处理”。")
add_step(doc, 5, "回到“异常记录”页面或首页，确认该记录已变为“已处理”。")
add_tip(doc, "提示", "顶部导航栏也有“异常记录”入口，点击可直达本页，适合班中快速查看。")

# ---------------- 7 详情 ----------------
add_heading(doc, "7　球化记录详情：复核与处理", 1)
add_para(doc,
         "在任意列表（球化记录、异常记录、首页最近记录）中点击“查看详情”，"
         "进入对应记录的详情页。详情页从上到下分为 4 个区块：")
add_figure(doc, "06_detail.png", "图 6　球化记录详情页（球化亮光分析曲线、基本信息、机器检测结果、复核与处理）")

add_heading(doc, "7.1　球化亮光分析曲线", 2)
add_para(doc,
         "详情页最上方显示该记录对应的“球化亮光分析曲线”图片——由检测系统根据铁水表面"
         "亮度变化生成的反应曲线，是判断球化是否充分的主要依据。"
         "若该记录没有上传图片，则显示“无照片”。")

add_heading(doc, "7.2　基本信息与机器检测结果", 2)
add_para(doc, "“基本信息”区块显示 6 个时间字段：")
add_bullet(doc, "检测时间、球化开始时间、球化结束时间、进线开始时间、进线结束时间、测温时间。")
add_para(doc, "“机器检测结果”区块显示机器判定的结论（正常 / 异常）以及关键数值：")
add_table(doc,
          ["字段", "含义"],
          [
              ["机器检测结果", "机器自动判定的结论（绿色“正常” / 红色“异常”）"],
              ["实际球化时间", "本次实际反应时长"],
              ["标准球化时间", "检测当时生效的标准值（快照，不会随标准调整变化）"],
              ["球化异常", "机器对球化环节的异常判断"],
              ["实际进线时间", "进线总时长"],
              ["铁水重量 / 温度", "本次检测的重量与温度"],
          ],
          widths=[5.0, 10.4])
add_rich(doc, [
    ("重要规则：", {"size": 10.5, "bold": True, "color": RED}),
    ("机器检测结果一经产生就永久保留，任何人工操作（包括复核）都不能修改它。",
     {"size": 10.5}),
])

add_heading(doc, "7.3　人工复核", 2)
add_para(doc, "“人工复核”区块分两部分：")
add_para(doc, "（1）复核记录列表：按时间列出该记录的全部复核，每条包含复核结论（正常/异常）、"
              "复核人、复核时间和复核说明。", bold=False)
add_para(doc, "（2）新增复核表单：")
add_table(doc,
          ["字段", "说明"],
          [
              ["复核结果", "下拉选择：正常 / 异常"],
              ["复核人", "填写复核人姓名（必填，不填会提示“请输入复核人”）"],
              ["复核说明", "填写判断依据或原因（必填，不填会提示“请输入复核说明”）"],
              ["提交复核", "点击后复核记录立即生效，刷新页面可见"],
          ],
          widths=[4.2, 11.2])
add_tip(doc, "说明", "同一条记录可以多次复核，历史复核记录都会保留，不会被覆盖。"
       "复核结论只记录在“复核状态”列，不影响“检测结果”列。")

add_heading(doc, "7.4　处理状态与“标记为已处理”", 2)
add_para(doc, "页面最下方是“处理状态”区块：")
add_bullet(doc, "未处理：显示输入框和“标记为已处理”按钮。填写处理人后点击按钮，"
                "记录立即变为“已处理”，并自动记录处理时间。")
add_bullet(doc, "已处理：显示处理人和处理时间，不再显示按钮。")
add_figure(doc, "07_detail_processed.png", "图 7　已处理的异常记录详情（含人工复核记录与处理信息）")
add_figure(doc, "08_detail_unprocessed.png", "图 8　未处理记录详情（可填写处理人并“标记为已处理”）")
add_rich(doc, [
    ("重要规则：", {"size": 10.5, "bold": True, "color": RED}),
    ("“标记为已处理”是一次性操作，不可回退。点击前请务必确认该异常已实际处置完成。",
     {"size": 10.5}),
])
add_tip(doc, "说明", "“复核”和“处理”是两件独立的事：复核了不一定代表已处理，"
       "处理了也不一定复核过。两者互不依赖、互不覆盖。")

# ---------------- 8 检测标准 ----------------
add_heading(doc, "8　检测标准管理", 1)
add_para(doc,
         "“检测标准”页面用于维护判定球化是否达标的标准值，分三个区块（见图 9）。")
add_figure(doc, "09_standard.png", "图 9　检测标准管理页面（当前生效标准、标准记录、新增标准表单）")

add_heading(doc, "8.1　查看当前生效标准", 2)
add_para(doc, "“当前生效标准”区块显示正在使用的标准：")
add_table(doc,
          ["字段", "含义"],
          [
              ["球化时间标准", "标准球化反应时长（秒）"],
              ["球化时间下限 / 上限", "允许的波动范围；“未设置”表示该方向没有限制"],
              ["称重标准", "铁水称重标准值"],
              ["创建时间 / 创建人", "该标准的创建信息与负责人"],
              ["备注", "调整原因或说明"],
          ],
          widths=[5.0, 10.4])
add_para(doc, "页面右上角有“刷新”按钮；当前标准永远是“最新创建”或“最近应用”的那一条。")

add_heading(doc, "8.2　应用历史标准", 2)
add_step(doc, 1, "在“标准记录”表格中找到要恢复使用的历史标准（当前标准显示为灰色“当前标准”按钮）。")
add_step(doc, 2, "点击该行的“应用标准”按钮。")
add_step(doc, 3, "弹出确认框：“应用后只影响之后创建的球化记录，历史记录不会改变。确认应用该标准吗？”")
add_step(doc, 4, "点击“确定”后，该标准立即成为当前生效标准。")
add_tip(doc, "说明", "“应用标准”只是把当前生效的标准切换回某个历史版本，"
       "所有历史标准都会保留，随时可以再次切换。")

add_heading(doc, "8.3　新增检测标准", 2)
add_step(doc, 1, "在“新增检测标准”表单中填写：球化时间标准、球化时间下限、球化时间上限、称重标准。")
add_step(doc, 2, "填写创建人，并在备注中说明调整原因（便于日后追溯）。")
add_step(doc, 3, "点击“创建标准”。新标准立即成为当前生效标准，并加入“标准记录”表格。")

add_heading(doc, "8.4　标准快照机制（重要）", 2)
add_rich(doc, [
    ("每一条球化检测记录在创建时，都会把当时的标准值“拍照”保存（标准快照）。",
     {"size": 10.5}),
], space_after=4)
add_bullet(doc, "之后无论标准怎么调整，历史记录里显示的“标准球化时间”永远是检测当时的值；")
add_bullet(doc, "新标准只对之后新产生的记录生效；")
add_bullet(doc, "因此“标准/实际球化时长”这一列的对比结果永远可信，不会事后变化。")

# ---------------- 9 常用业务流程 ----------------
add_heading(doc, "9　常用业务流程", 1)

add_heading(doc, "9.1　流程一：班中巡检", 2)
add_step(doc, 1, "打开“浇注工位监控”页面，查看两个摄像头画面是否正常。")
add_step(doc, 2, "查看最新 5 条检测数据，重点看“球化结果”列和底部状态栏。")
add_step(doc, 3, "发现“异常”且“待处理”的记录，按流程二处理。")

add_heading(doc, "9.2　流程二：处理一条异常记录", 2)
add_step(doc, 1, "进入“异常记录”页面，找到待处理记录，点击“查看详情”。")
add_step(doc, 2, "查看“球化亮光分析曲线”和机器检测结果，判断异常原因。")
add_step(doc, 3, "填写人工复核：复核结论、复核人、复核说明，点击“提交复核”。")
add_step(doc, 4, "现场处置完成后，填写处理人，点击“标记为已处理”。")
add_step(doc, 5, "在首页统计卡片确认“未处理”数量减少、“已处理”增加。")

add_heading(doc, "9.3　流程三：调整检测标准", 2)
add_step(doc, 1, "工艺变更时，进入“检测标准”页面。")
add_step(doc, 2, "填写“新增检测标准”表单并“创建标准”（立即生效），"
                 "或在“标准记录”中“应用标准”切回旧版本。")
add_step(doc, 3, "检查“当前生效标准”区块，确认数值与生效时间无误。")
add_tip(doc, "说明", "标准调整不需要重启系统，创建或应用后立即对新记录生效；"
       "历史记录的快照不受影响。")

# ---------------- 10 FAQ ----------------
add_heading(doc, "10　常见问题（FAQ）", 1)
faqs = [
    ("检测记录需要我手工录入吗？",
     "不需要。检测记录正常由上游检测模块自动推送生成；只有在检测模块未推送、确需补录时，"
     "才用“新增记录”手工补录。非必要不要新增，以免产生重复记录、影响统计与质量追溯。"),
    ("页面右上角显示“系统离线”或一直“连接中”？",
     "说明前端连不上后端服务（端口 8000）。请确认后端服务已启动、网络正常；"
     "也可以点击状态按钮重新检测。仍不行请联系系统管理员。"),
    ("视频窗口显示“等待视频流接入”？",
     "摄像头或视频流服务尚未上线。画面接入后窗口会自动显示实时视频，无需刷新或重启页面。"),
    ("页面提示“无法连接后端服务”或“加载失败”？",
     "后端服务未启动或地址配置错误。请系统管理员检查后端进程与代理配置。"),
    ("列表里某些列显示“--”是什么？",
     "老记录没有采集这些字段时的占位显示，属于正常现象，不代表数据丢失。"),
    ("人工复核能把“异常”改成“正常”吗？",
     "不能。机器检测结果永久保留；复核结论单独保存在“复核状态”列，"
     "两者同时存在、互不覆盖。"),
    ("“标记为已处理”之后能撤销吗？",
     "不能。处理状态为一次性操作，不可回退，点击前请确认已实际处置。"),
    ("一条记录可以复核多次吗？",
     "可以。每次复核都会新增一条复核记录，历史复核全部保留。"),
    ("新创建/应用的标准会影响历史记录吗？",
     "不会。历史记录保留检测当时的标准快照；标准调整只影响之后新产生的记录。"),
    ("球化图片支持哪些格式？",
     "目前只支持 JPG（.jpg / .jpeg），其他格式会被拒绝并提示。"),
    ("“异常记录”页面和“球化记录”页面有什么区别？",
     "布局相同；区别是异常记录页自动只筛选机器判“异常”的记录，且“检测结果”条件不可修改。"),
]
for q, a in faqs:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    style_run(p.add_run("问：" + q), size=10.5, bold=True)
    pa = doc.add_paragraph()
    pa.paragraph_format.space_after = Pt(4)
    pa.paragraph_format.line_spacing = 1.35
    pa.paragraph_format.left_indent = Cm(0.5)
    style_run(pa.add_run("答：" + a), size=10.5)

# ---------------- 11 附录 ----------------
add_heading(doc, "11　附录：名词解释", 1)
add_table(doc,
          ["名词", "解释"],
          [
              ["球化", "球化处理：改变铸铁中石墨形态的热处理工艺，使石墨呈球状分布，提高铸铁韧性"],
              ["球化时间", "从球化反应开始到结束所经历的时间（秒）"],
              ["标准球化时间", "工艺规定的标准球化时间，可设置上下限作为判定范围"],
              ["进线", "球化剂进线（送线）过程，记录其开始/结束时刻与总时长"],
              ["球化重量（铁水重量）", "本次检测对应铁水的重量"],
              ["球化温度（铁水温度）", "检测时铁水的温度（℃）"],
              ["球化亮光分析曲线", "检测系统根据铁水表面亮度变化生成的反应曲线图，用于判断球化效果"],
              ["标准快照", "检测记录创建时自动保存的“当时标准值”，保证历史记录可追溯"],
              ["人工复核", "人员对机器检测结果进行确认并记录结论的操作，与机器结果分开保存"],
              ["处理", "对异常记录完成实际处置后，在系统中“标记为已处理”（记录处理人与时间）"],
          ],
          widths=[4.6, 10.8])
add_para(doc, "", space_after=10)
add_para(doc, "—— 全文完 ——", size=10, color=GREY, align=WD_ALIGN_PARAGRAPH.CENTER)

doc.save(OUT)
clean_doc_props(OUT)
print("saved:", OUT, os.path.getsize(OUT), "bytes")
