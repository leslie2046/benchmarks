from pathlib import Path
from math import ceil

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output" / "pdf" / "p40-vs-l20-benchmark-report.pdf"

pdfmetrics.registerFont(TTFont("YaHei", r"C:\Windows\Fonts\msyh.ttc"))
pdfmetrics.registerFont(TTFont("YaHeiBold", r"C:\Windows\Fonts\msyhbd.ttc"))

PAGE_W, PAGE_H = A4
NAVY = colors.HexColor("#17233D")
BLUE = colors.HexColor("#2563EB")
ORANGE = colors.HexColor("#EA580C")
CYAN = colors.HexColor("#0891B2")
INK = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#667085")
GRID = colors.HexColor("#DCE3EC")
PALE = colors.HexColor("#F4F7FB")
PALE_BLUE = colors.HexColor("#EAF1FF")
PALE_ORANGE = colors.HexColor("#FFF1E9")
GREEN = colors.HexColor("#14804A")
RED = colors.HexColor("#C9372C")


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="CoverTitle", fontName="YaHeiBold", fontSize=27, leading=38,
    textColor=NAVY, alignment=TA_LEFT, spaceAfter=12,
))
styles.add(ParagraphStyle(
    name="CoverSub", fontName="YaHei", fontSize=13, leading=21,
    textColor=MUTED, alignment=TA_LEFT,
))
styles.add(ParagraphStyle(
    name="H1CN", fontName="YaHeiBold", fontSize=20, leading=28,
    textColor=NAVY, spaceAfter=10,
))
styles.add(ParagraphStyle(
    name="H2CN", fontName="YaHeiBold", fontSize=14, leading=21,
    textColor=NAVY, spaceBefore=7, spaceAfter=7,
))
styles.add(ParagraphStyle(
    name="BodyCN", fontName="YaHei", fontSize=9.2, leading=15,
    textColor=INK, spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="SmallCN", fontName="YaHei", fontSize=7.5, leading=11,
    textColor=MUTED,
))
styles.add(ParagraphStyle(
    name="Callout", fontName="YaHei", fontSize=10, leading=17,
    textColor=NAVY, backColor=PALE_BLUE, borderColor=BLUE,
    borderWidth=0.7, borderPadding=9, spaceBefore=5, spaceAfter=10,
))
styles.add(ParagraphStyle(
    name="Warn", fontName="YaHei", fontSize=9.2, leading=15,
    textColor=INK, backColor=PALE_ORANGE, borderColor=ORANGE,
    borderWidth=0.7, borderPadding=8, spaceBefore=5, spaceAfter=9,
))
styles.add(ParagraphStyle(
    name="MetricValue", fontName="YaHeiBold", fontSize=18, leading=23,
    textColor=NAVY, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="MetricLabel", fontName="YaHei", fontSize=8, leading=12,
    textColor=MUTED, alignment=TA_CENTER,
))


class DualAxisChart(Flowable):
    def __init__(self, title, qps, p50, width=170*mm, height=74*mm):
        super().__init__()
        self.title = title
        self.qps = qps
        self.p50 = p50
        self.width = width
        self.height = height

    @staticmethod
    def nice_max(value):
        if value <= 10:
            step = 2
        elif value <= 50:
            step = 10
        elif value <= 100:
            step = 20
        elif value <= 300:
            step = 50
        else:
            step = 100
        return max(step, ceil(value / step) * step)

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        left, right, bottom, top = 38, 43, 29, 35
        x0, x1 = left, w - right
        y0, y1 = bottom, h - top
        qmax = self.nice_max(max(v for values in self.qps.values() for _, v in values) * 1.05)
        pmax = self.nice_max(max(v for values in self.p50.values() for _, v in values) * 1.05)

        c.setFont("YaHeiBold", 10.5)
        c.setFillColor(NAVY)
        c.drawString(0, h - 12, self.title)

        # Legend
        legend_y = h - 25
        entries = [
            (BLUE, False, "P40 QPS"), (ORANGE, False, "L20 QPS"),
            (BLUE, True, "P40 P50"), (ORANGE, True, "L20 P50"),
        ]
        lx = x0
        for color, dashed, label in entries:
            c.setStrokeColor(color)
            c.setLineWidth(1.8)
            c.setDash(4, 3) if dashed else c.setDash()
            c.line(lx, legend_y, lx + 15, legend_y)
            c.setDash()
            c.setFillColor(INK)
            c.setFont("YaHei", 7)
            c.drawString(lx + 19, legend_y - 2.5, label)
            lx += 78

        # Frame and grid
        c.setStrokeColor(GRID)
        c.setLineWidth(0.6)
        for i in range(6):
            yy = y0 + (y1 - y0) * i / 5
            c.line(x0, yy, x1, yy)
        c.setStrokeColor(colors.HexColor("#9AA6B6"))
        c.rect(x0, y0, x1 - x0, y1 - y0, fill=0, stroke=1)

        c.setFont("YaHei", 6.8)
        for i in range(6):
            yy = y0 + (y1 - y0) * i / 5
            c.setFillColor(BLUE)
            c.drawRightString(x0 - 5, yy - 2.5, f"{qmax * i / 5:.0f}")
            c.setFillColor(ORANGE)
            c.drawString(x1 + 5, yy - 2.5, f"{pmax * i / 5:.0f}")
        c.setFillColor(BLUE)
        c.setFont("YaHeiBold", 7.3)
        c.drawString(0, y1 + 2, "QPS")
        c.setFillColor(ORANGE)
        c.drawRightString(w, y1 + 2, "P50 (ms)")

        conc = [1, 5, 10]
        def sx(x):
            return x0 + (x - 1) / 9 * (x1 - x0)
        def sy_q(v):
            return y0 + v / qmax * (y1 - y0)
        def sy_p(v):
            return y0 + v / pmax * (y1 - y0)

        c.setFillColor(MUTED)
        c.setFont("YaHei", 7)
        for x in conc:
            c.drawCentredString(sx(x), y0 - 12, str(x))
        c.drawCentredString((x0 + x1) / 2, 3, "并发数")

        for gpu, color in (("P40", BLUE), ("L20", ORANGE)):
            for values, yfunc, dashed, square in (
                (self.qps[gpu], sy_q, False, False),
                (self.p50[gpu], sy_p, True, True),
            ):
                c.setStrokeColor(color)
                c.setFillColor(color)
                c.setLineWidth(1.8)
                c.setDash(4, 3) if dashed else c.setDash()
                pts = [(sx(x), yfunc(v)) for x, v in values]
                for a, b in zip(pts, pts[1:]):
                    c.line(a[0], a[1], b[0], b[1])
                c.setDash()
                for px, py in pts:
                    if square:
                        c.rect(px - 2.3, py - 2.3, 4.6, 4.6, fill=1, stroke=0)
                    else:
                        c.circle(px, py, 2.5, fill=1, stroke=0)


def P(text, style="BodyCN"):
    return Paragraph(text, styles[style])


def metric_cards(items):
    cells = [
        [P(value, "MetricValue") for value, _ in items],
        [P(label, "MetricLabel") for _, label in items],
    ]
    card_table = Table(cells, colWidths=[(170*mm)/len(items)]*len(items), rowHeights=[11*mm, 9*mm])
    card_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.5, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return card_table


def data_table(headers, rows, widths, highlight_cols=(4,)):
    formatted = [[P(str(h), "SmallCN") for h in headers]]
    for row in rows:
        formatted.append([P(str(v), "SmallCN") for v in row])
    t = Table(formatted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "YaHeiBold"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for col in highlight_cols:
        commands.append(("FONTNAME", (col, 1), (col, -1), "YaHeiBold"))
    t.setStyle(TableStyle(commands))
    return t


def bullets(items):
    return [P(f"• {item}") for item in items]


def page_decor(canvas, doc):
    canvas.saveState()
    page = canvas.getPageNumber()
    if page > 1:
        canvas.setStrokeColor(GRID)
        canvas.setLineWidth(0.5)
        canvas.line(20*mm, PAGE_H - 15*mm, PAGE_W - 20*mm, PAGE_H - 15*mm)
        canvas.setFont("YaHei", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(20*mm, PAGE_H - 11.5*mm, "P40 与 L20 单 Worker 推理性能测试")
        canvas.drawRightString(PAGE_W - 20*mm, 11*mm, f"第 {page} 页")
    canvas.restoreState()


embedding_qps = {
    "P40": [(1, 11.34), (5, 28.90), (10, 32.43)],
    "L20": [(1, 22.49), (5, 28.68), (10, 12.62)],
}
embedding_p50 = {
    "P40": [(1, 72.69), (5, 97.37), (10, 139.46)],
    "L20": [(1, 39.49), (5, 91.49), (10, 151.88)],
}
reranker_qps = {
    "P40": [(1, 8.48), (5, 13.24), (10, 13.39)],
    "L20": [(1, 19.27), (5, 80.49), (10, 73.96)],
}
reranker_p50 = {
    "P40": [(1, 100.41), (5, 300.07), (10, 542.39)],
    "L20": [(1, 46.10), (5, 57.26), (10, 92.64)],
}
audio_qps = {
    "P40": [(1, 0.84), (5, 0.93)],
    "L20": [(1, 2.28), (5, 2.76), (10, 2.76)],
}
audio_p50 = {
    "P40": [(1, 1173.86), (5, 5319.40)],
    "L20": [(1, 438.36), (5, 1761.76), (10, 3523.05)],
}


story = []

# Cover
story += [Spacer(1, 34*mm)]
story.append(P("P40 与 L20 推理性能测试报告", "CoverTitle"))
story.append(P("Embedding · Reranker · Audio Transcription", "CoverSub"))
story.append(Spacer(1, 16*mm))
story.append(Table([[""], [""]], colWidths=[36*mm], rowHeights=[2.8*mm, 2.8*mm], style=TableStyle([
    ("BACKGROUND", (0, 0), (0, 0), BLUE),
    ("BACKGROUND", (0, 1), (0, 1), ORANGE),
])))
story.append(Spacer(1, 18*mm))
story.append(metric_cards([
    ("1 vs 1", "部署口径：每端 1 个 worker"),
    ("100 次", "每组正式请求数"),
    ("P50", "主要延迟指标"),
]))
story.append(Spacer(1, 18*mm))
story.append(P("报告日期：2026-09-17", "CoverSub"))
story.append(P("测试环境：客户端位于 Asia/Shanghai；P40 使用 HTTPS，L20 使用 HTTP。", "CoverSub"))
story.append(Spacer(1, 20*mm))
story.append(P("结论摘要", "H2CN"))
story.append(P("L20 在 Reranker 和 Audio 上有显著优势；Embedding 的优势随并发变化，L20 在并发 1 更快，P40 在并发 10 的持续吞吐更高。", "Callout"))
story.append(PageBreak())

# Method and executive summary
story.append(P("1. 测试范围与方法", "H1CN"))
story.append(P("本报告汇总两端均只部署 1 个 worker 后的重测结果。每种模型分别测试并发 1、5、10，每组发送 100 次请求。预热请求不计入正式结果。所有可比较组均使用相同输入与客户端脚本。"))
method_rows = [
    ["项目", "模型 / 输入", "请求口径"],
    ["Embedding", "bge-m3", "单文本 embedding；脚本内置 10 条英文样本"],
    ["Reranker", "bge-reranker-large", "1 query + 10 documents；Top 4；不传 batch_size 扩展参数"],
    ["Audio", "seaco-paraformer-zh", "audio/bill_gates-TED.mp3；时长 62.06 秒"],
]
mt = Table([[P(x, "SmallCN") for x in row] for row in method_rows], colWidths=[28*mm, 47*mm, 95*mm], repeatRows=1)
mt.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
    ("FONTNAME", (0,0), (-1,0), "YaHeiBold"), ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, PALE]),
    ("LINEBELOW", (0,1), (-1,-1), 0.35, GRID),
    ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
    ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
]))
story.append(mt)
story.append(Spacer(1, 6*mm))
story.append(P("关键结论", "H2CN"))
story += bullets([
    "Embedding：并发 1 时 L20 QPS 为 P40 的 1.98 倍；并发 5 基本持平；并发 10 时 P40 QPS 为 L20 三轮中位数的 2.57 倍。",
    "Reranker：L20 在并发 1、5、10 下吞吐分别为 P40 的 2.27、6.08、5.52 倍，且 P50 全面更低。",
    "Audio：在可公平比较的并发 1 和 5 下，L20 吞吐为 P40 的 2.71 和 2.97 倍。",
    "Audio 并发 10：P40 服务端 request_limit=5，100 次请求仅 13 次成功，该组不能用于 GPU 性能比较。",
])
story.append(P("说明：P40 经 HTTPS、L20 经 HTTP。对于 Embedding 和 Reranker 这类小请求，TLS、网关与网络路径可能对端到端延迟产生可见影响，因此报告衡量的是当前服务整体表现，不是脱离服务栈的裸 GPU 算力。", "Warn"))
story.append(PageBreak())

# Embedding
story.append(P("2. Embedding 性能", "H1CN"))
story.append(P("模型：bge-m3。图中实线对应左轴 QPS，虚线对应右轴 P50 延迟。L20 并发 10 使用三轮重测的中位数，以降低偶发长尾对单轮结果的影响。"))
story.append(DualAxisChart("Embedding 双纵轴曲线", embedding_qps, embedding_p50))
story.append(Spacer(1, 3*mm))
embedding_rows = [
    ["P40", 1, "100%", "11.34", "72.69", "101.26", "799.50"],
    ["L20", 1, "100%", "22.49", "39.49", "50.01", "379.54"],
    ["P40", 5, "100%", "28.90", "97.37", "1034.36", "1045.13"],
    ["L20", 5, "100%", "28.68", "91.49", "488.87", "1466.37"],
    ["P40", 10, "100%", "32.43", "139.46", "1800.20", "1818.92"],
    ["L20", 10, "100%", "12.62*", "151.88*", "1069.67*", "7652.70*"],
]
story.append(data_table(
    ["GPU", "并发", "成功率", "QPS", "P50 ms", "P95 ms", "P99 ms"],
    embedding_rows, [20*mm, 15*mm, 23*mm, 23*mm, 27*mm, 29*mm, 29*mm], highlight_cols=(3,4),
))
story.append(P("* L20 并发 10 为 3 轮各 100 次重测的中位数。三轮 QPS 为 12.56、23.00、12.62；合计吞吐为 14.82 QPS。P50 较稳定，但存在 4 到 8 秒的偶发长尾。", "SmallCN"))
story.append(P("判断：L20 的低并发响应更快；P40 在高并发下吞吐扩展更好。若业务重视稳定性，应同时监控 P95/P99，而不是只看 P50。", "Callout"))
story.append(PageBreak())

# Reranker
story.append(P("3. Reranker 性能", "H1CN"))
story.append(P("模型：bge-reranker-large。每个请求包含 1 个 query 和 10 个 documents，返回 Top 4。两端统一省略 L20 不兼容的 kwargs.batch_size 扩展参数。"))
story.append(DualAxisChart("Reranker 双纵轴曲线", reranker_qps, reranker_p50))
story.append(Spacer(1, 3*mm))
reranker_rows = [
    ["P40", 1, "100%", "8.48", "100.41", "140.50", "744.02"],
    ["L20", 1, "100%", "19.27", "46.10", "57.23", "425.45"],
    ["P40", 5, "100%", "13.24", "300.07", "1259.56", "1278.76"],
    ["L20", 5, "100%", "80.49", "57.26", "94.15", "113.96"],
    ["P40", 10, "100%", "13.39", "542.39", "2121.71", "2129.49"],
    ["L20", 10, "100%", "73.96", "92.64", "476.70", "478.56"],
]
story.append(data_table(
    ["GPU", "并发", "成功率", "QPS", "P50 ms", "P95 ms", "P99 ms"],
    reranker_rows, [20*mm, 15*mm, 23*mm, 23*mm, 27*mm, 29*mm, 29*mm], highlight_cols=(3,4),
))
story.append(Spacer(1, 4*mm))
story.append(metric_cards([
    ("6.08×", "并发 5：L20 吞吐倍数"),
    ("80.9%", "并发 5：L20 P50 降幅"),
    ("5", "L20 推荐并发点"),
]))
story.append(P("判断：L20 在 Reranker 上全面领先。L20 从并发 5 提升到 10 后 QPS 从 80.49 降到 73.96，同时 P50 上升，因此当前最佳客户端并发约为 5。P40 在并发 5 左右已经饱和。", "Callout"))
story.append(PageBreak())

# Audio
story.append(P("4. Audio Transcription 性能", "H1CN"))
story.append(P("模型：seaco-paraformer-zh。音频文件 bill_gates-TED.mp3，时长 62.06 秒。RTF 为处理耗时除以音频时长，越低越好。"))
story.append(DualAxisChart("Audio 双纵轴曲线（P40 并发 10 因限流未绘制）", audio_qps, audio_p50))
story.append(Spacer(1, 3*mm))
audio_rows = [
    ["P40", 1, "100%", "0.84", "1173.86", "1364.41", "1888.46", "0.019"],
    ["L20", 1, "100%", "2.28", "438.36", "464.83", "600.29", "0.007"],
    ["P40", 5, "100%", "0.93", "5319.40", "5531.67", "6724.90", "0.085"],
    ["L20", 5, "100%", "2.76", "1761.76", "2206.69", "3021.16", "0.029"],
    ["P40", 10, "13%", "无效", "无效", "无效", "无效", "无效"],
    ["L20", 10, "100%", "2.76", "3523.05", "3861.98", "4537.86", "0.056"],
]
story.append(data_table(
    ["GPU", "并发", "成功率", "QPS", "P50 ms", "P95 ms", "P99 ms", "RTF"],
    audio_rows, [18*mm, 13*mm, 20*mm, 20*mm, 25*mm, 25*mm, 25*mm, 18*mm], highlight_cols=(3,4,7),
))
story.append(P("P40 并发 10 返回 HTTP 429：模型 seaco-paraformer-zh-rep0 的 request limit 为 5。快速失败请求会扭曲脚本输出的 QPS 与延迟，因此该组不展示性能数值。", "Warn"))
story.append(P("判断：在并发 1 和 5 的有效范围内，L20 吞吐约为 P40 的 2.7 到 3.0 倍。L20 在并发 5 已达到 2.76 QPS；升至并发 10 后吞吐没有增加，P50 从 1.76 秒上升至 3.52 秒。", "Callout"))
story.append(PageBreak())

# Recommendations
story.append(P("5. 结论与建议", "H1CN"))
story.append(P("选型结论", "H2CN"))
summary_rows = [
    ["场景", "建议", "依据"],
    ["Embedding 低并发", "优先 L20", "并发 1 时 QPS 约 1.98 倍，P50 低 45.7%"],
    ["Embedding 高并发", "当前配置优先 P40", "并发 10 时 P40 QPS 32.43；L20 三轮中位数 12.62"],
    ["Reranker", "优先 L20", "全并发区间吞吐和 P50 均显著领先"],
    ["Audio", "优先 L20", "有效区间吞吐约为 P40 的 2.7 到 3.0 倍"],
]
st = Table([[P(x, "SmallCN") for x in row] for row in summary_rows], colWidths=[38*mm, 42*mm, 90*mm], repeatRows=1)
st.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
    ("FONTNAME", (0,0), (-1,0), "YaHeiBold"), ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, PALE]),
    ("LINEBELOW", (0,1), (-1,-1), 0.35, GRID),
    ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
    ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
]))
story.append(st)
story.append(Spacer(1, 7*mm))
story.append(P("部署与压测建议", "H2CN"))
story += bullets([
    "对齐模型级 request_limit。若要比较 Audio 并发 10，P40 与 L20 都应配置为至少 10。",
    "每个并发点至少重复 3 轮，以轮次中位数作为主结果，并同时报告合计吞吐。",
    "固定输入序列与随机种子，避免不同文本长度造成额外波动。",
    "服务端同步采集 GPU 利用率、显存、队列长度和批处理大小，以区分 GPU 饱和、调度排队和网络抖动。",
    "对小请求增加同网络路径测试，或统一 HTTPS/HTTP 和网关配置，降低传输层差异。",
    "生产容量规划同时参考 QPS、P50、P95/P99 和错误率；不以单一平均延迟做结论。",
])
story.append(Spacer(1, 6*mm))
story.append(P("最终结论", "H2CN"))
story.append(P("在当前单 worker 服务配置下，L20 是 Reranker 与 Audio 的明确优选；Embedding 则取决于并发模式：低并发偏向 L20，高并发持续吞吐偏向 P40。对于 L20 Embedding 并发 10，应继续调查 4 到 8 秒的周期性长尾。", "Callout"))
story.append(Spacer(1, 8*mm))
story.append(P("附注：本报告中的测试结果来自客户端端到端观测，包含模型执行、调度、网关、网络和协议开销。API Key 未写入报告。", "SmallCN"))


doc = SimpleDocTemplate(
    str(OUTPUT), pagesize=A4,
    rightMargin=20*mm, leftMargin=20*mm,
    topMargin=21*mm, bottomMargin=17*mm,
    title="P40 与 L20 推理性能测试报告",
    author="OpenAI Codex",
    subject="单 Worker Embedding、Reranker 与 Audio 性能比较",
)
doc.build(story, onFirstPage=page_decor, onLaterPages=page_decor)
print(OUTPUT)
