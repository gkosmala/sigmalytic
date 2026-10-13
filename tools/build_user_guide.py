"""Builds frontend/assets/Sigmalytic_V2_User_Guide.pdf (the guide the User Guide tab embeds).

    python3 tools/build_user_guide.py

Edit the text below, run the script, commit the PDF. The cover banner is tools/user_guide_banner.png.
The guide describes labels and behavior as they appear in the app; keep it in step with the UI.
"""
from __future__ import annotations

import os
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, NextPageTemplate, PageBreak, PageTemplate, Paragraph,
                                Spacer)
from reportlab.platypus.tableofcontents import TableOfContents

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "frontend", "assets", "Sigmalytic_V2_User_Guide.pdf")
BANNER = os.path.join(HERE, "user_guide_banner.png")
EDITION = "October 13, 2026"

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
for name, f in (("DV", "DejaVuSans.ttf"), ("DV-B", "DejaVuSans-Bold.ttf"), ("DV-I", "DejaVuSans-Oblique.ttf"),
                ("DV-BI", "DejaVuSans-BoldOblique.ttf")):
    pdfmetrics.registerFont(TTFont(name, os.path.join(FONT_DIR, f)))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV-I", boldItalic="DV-BI")

TEAL = colors.HexColor("#0E6B63")
GREY = colors.HexColor("#777777")
BODY = ParagraphStyle("body", fontName="DV", fontSize=9.3, leading=13.0, spaceAfter=5.5)
H1 = ParagraphStyle("h1", fontName="DV-B", fontSize=17, leading=22, textColor=TEAL, spaceBefore=4, spaceAfter=8)
H2 = ParagraphStyle("h2", fontName="DV-B", fontSize=11.2, leading=15, textColor=TEAL, spaceBefore=8, spaceAfter=4)
H3 = ParagraphStyle("h3", fontName="DV-B", fontSize=9.8, leading=14, textColor=TEAL, spaceBefore=6, spaceAfter=3)
BUL = ParagraphStyle("bul", parent=BODY, leftIndent=20, bulletIndent=2, spaceAfter=3.2)
GLOSS = ParagraphStyle("gloss", parent=BODY, spaceAfter=4.5)
C_ = ParagraphStyle("c", fontName="DV", fontSize=9.6, leading=14, alignment=TA_CENTER, spaceAfter=10)
CB = ParagraphStyle("cb", parent=C_, fontName="DV-B")
CI = ParagraphStyle("ci", parent=C_, fontName="DV-I")
TOC1 = ParagraphStyle("toc1", fontName="DV-B", fontSize=9.6, leading=12, spaceBefore=6, leftIndent=0)
TOC2 = ParagraphStyle("toc2", fontName="DV", fontSize=8.3, leading=11, spaceBefore=1.5, leftIndent=12)


class Doc(BaseDocTemplate):
    def __init__(self, path, **kw):
        super().__init__(path, pagesize=letter, leftMargin=74, rightMargin=74, topMargin=66, bottomMargin=58,
                         title="Sigmalytic V2 — User Guide", author="Sigmalytic Quant Corporation", **kw)
        fr = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f", leftPadding=0, rightPadding=0,
                   topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="cover", frames=[fr]),
                               PageTemplate(id="body", frames=[fr], onPage=self._decor)])

    @staticmethod
    def _decor(canv, doc):
        canv.saveState()
        canv.setFont("DV", 6.6)
        canv.setFillColor(GREY)
        canv.drawCentredString(letter[0] / 2, letter[1] - 36, "Sigmalytic V2 — User Guide")
        canv.drawCentredString(letter[0] / 2, 30, f"© 2026 Sigmalytic Quant Corporation. All rights reserved. Confidential. · {doc.page}")
        canv.restoreState()

    def afterFlowable(self, fl):
        sty = getattr(fl, "style", None)
        if sty is None or not isinstance(fl, Paragraph):
            return
        key = f"{sty.name}-{self.page}-{id(fl)}"
        if sty.name == "h1" and getattr(fl, "_toc", True):
            self.notify("TOCEntry", (0, fl.getPlainText(), self.page, key))
            self.canv.bookmarkPage(key)
        elif sty.name == "h2n":
            self.notify("TOCEntry", (1, fl.getPlainText(), self.page, key))
            self.canv.bookmarkPage(key)


H2N = ParagraphStyle("h2n", parent=H2, fontSize=11.6, spaceBefore=10)   # numbered section heading, listed in the contents

story = []


def p(text, style=BODY):
    story.append(Paragraph(text, style))


def h1(text, break_before=False):
    if break_before:
        story.append(PageBreak())
    story.append(Paragraph(text, H1))


def h2(text):
    story.append(Paragraph(text, H2))


def h3(text):
    story.append(Paragraph(text, H3))


def sec(text):
    story.append(Paragraph(text, H2N))


def bullets(items):
    for t in items:
        story.append(Paragraph(t, BUL, bulletText="•"))


def gloss(entries):
    for term, text in entries:
        story.append(Paragraph(f"<b>{term}</b> — {text}", GLOSS))


# ───────────────────────────── cover ─────────────────────────────
story.append(NextPageTemplate("cover"))
story.append(Spacer(1, 1.45 * inch))
story.append(Image(BANNER, width=letter[0], height=letter[0] * 255 / 950))
story[-1].hAlign = "CENTER"
story.append(Spacer(1, 1.1 * inch))
p("Decision Intelligence Platform", C_)
p("User Guide", CB)
story.append(Spacer(1, 6))
p("Market structure, live charts, opportunity discovery, reports, and trading behavior<br/>in one decision intelligence platform.", CI)
story.append(Spacer(1, 12))
p(EDITION, CB)
p("Version 2.0 · Updated edition", C_)
p("Confidential — For Sigmalytic Users Only", C_)
story.append(Spacer(1, 0.9 * inch))
p("© 2026 Sigmalytic Quant Corporation. All rights reserved.", C_)
p("This guide and the Sigmalytic application are protected by copyright. No part of this guide may be copied, "
  "distributed, or reused without prior written permission.", C_)
story.append(NextPageTemplate("body"))
story.append(PageBreak())

# ───────────────────────────── contents ─────────────────────────────
story.append(Paragraph("Table of Contents", ParagraphStyle("tochead", parent=H1)))
toc = TableOfContents()
toc.dotsMinLevel = 0
toc.levelStyles = [TOC1, TOC2]
story.append(toc)

# ───────────────────────────── chapter 1 ─────────────────────────────
h1("Chapter 1 — Introduction", break_before=True)
h2("What Sigmalytic does")
p("Sigmalytic helps you narrow a broad market of price and volume activity into opportunities worth a closer look. "
  "The platform combines a live single-symbol workspace, a structural-pattern radar, a multi-chart opportunity "
  "workspace, wave and Wyckoff analysis, reports, alerts, Behavioral Intelligence, which grades your own trading "
  "decisions, and Broker Behavioral Intelligence, which grades your broker or advisor. Its purpose is to help you find "
  "potential “trades about to happen” and review the supporting evidence efficiently.")
p("A scan can point to a symbol; the Command Center then lets you inspect its quote, candles, volume, and nearby "
  "structural levels. Sigma Analysis keeps distinct time-bar, Renko, point-and-figure (PnF), and Wyckoff readings "
  "visible without reducing them to one answer. Heat Map adds sector and industry context. This sequence is designed "
  "to save time while still showing what evidence produced your view.")
h2("Behavioral Intelligence")
p("Behavioral Intelligence is the part of Sigmalytic that follows the trader rather than the market, and it is "
  "proprietary to the platform. Most tools stop at the signal. Sigmalytic also grades what you did with it. Every "
  "recorded or imported trade is scored on its entry and exit quality, and the scores roll up into a Trader Behavioral "
  "Profile: an overall decision score plus separate Execution, Discipline, Timing, and Risk Management scores. The "
  "profile also shows warnings, your most common behavior pattern, and how your results differ across market regimes.")
p("You can build the profile in two ways. Record trades as you make them with the Journal or the Command Center, or "
  "upload a brokerage statement in Import History. Sigmalytic reads supported broker and generic CSV exports, "
  "reconstructs your history, and grades the trades whether you or your broker placed them. A correct signal still "
  "loses money when the execution is weak, so the profile is designed to help you see repeatable habits and improve "
  "them over many decisions rather than judging a single trade.")
p("A stated plan, a recorded entry or exit, imported history, and Journal records all feed the profile. Reports and "
  "alerts help you return to the market and to the decisions you have already made.")
h2("Broker Behavioral Intelligence")
p("Sigmalytic reviews both sides of an account: you, and the broker or advisor who may be trading or managing it for "
  "you. Broker Behavioral Intelligence applies the same A–F trade grading to the statements of up to five accounts, "
  "one in each vault, and adds portfolio health, fees, cash, and a comparison with the Russell 1000 (an index of the "
  "1,000 largest publicly traded U.S. companies by market capitalization). For every Russell 1000 stock the broker "
  "bought or sold, it also shows what Sigmalytic’s engines read on the day of the trade.")
p("This matters because a profitable account does not prove good management, and a losing account does not prove poor "
  "management. Grading the decisions, the behavior, and the cost separately helps you see whether the person handling "
  "your money is adding value, and gives you specific questions to ask. Many accounts are managed by someone else, so "
  "reviewing only the account holder would miss half of the picture.")
p("The platform presents research and market-structure information. A displayed pattern, grade, score, wall, or price "
  "level is context for your own decision, not an order or a promised outcome. Data availability varies by symbol, "
  "session, subscription, and upstream feed. Always read the timestamp and any unavailable-data message before relying "
  "on a display.")
h2("Not investment advice")
p("Sigmalytic is a research and decision-support platform. Nothing in the platform or in this guide is investment, "
  "financial, legal, or tax advice, a recommendation to buy or sell any security, or an offer or solicitation of any "
  "kind. Sigmalytic does not place orders or execute trades for you. Patterns, grades, scores, and past results do not "
  "guarantee future results, and trading involves risk, including the loss of the money you invest. You are solely "
  "responsible for your own trading decisions. Consider speaking with a licensed financial professional before you "
  "act.")

h2("Who this guide is for")
p("This guide is for subscribers and demo users. The main procedures describe controls available on the current "
  "customer interface. The Admin tab is described briefly for orientation; operational settings and manual jobs belong "
  "to administrators.")
h2("How to use this guide")
p("Chapter 2 gets you into the interface. Chapter 3 suggests a repeatable daily and weekly workflow. Chapter 4 "
  "explains each currently visible tab and its controls, including Broker Behavioral Intelligence. Chapter 5 defines "
  "terms that appear in the app. Chapter 6 provides support and copyright information. Appendix A offers worked "
  "examples.")

# ───────────────────────────── chapter 2 ─────────────────────────────
h1("Chapter 2 — Getting Started")
h2("Sign in and open the workspace")
bullets([
    "Open Sigmalytic in a modern browser and select <b>Sign In</b> with your account email and password. The sign-in "
    "screen also offers <b>Sign Up</b>, <b>Forgot your password?</b>, and <b>Try Demo — No Sign Up Required</b>.",
    "Your sign-in lasts for the current browser tab only. If you close the tab or the browser, sign in again. If you "
    "are not signed in, the app can open the shared demo account, where Journal and Portfolio appear empty; sign out and "
    "sign in again to see your own data.",
    "Start at Welcome; use <b>Open User Guide</b> for this PDF. Use the horizontal tab bar to move between workspaces. "
    "Some account or trading actions require a signed-in subscriber account.",
    "To study a ticker, type its symbol in the top field and click <b>Load Symbol</b>. The header displays a live price "
    "and buttons for 1m, 5m, 15m, 1H, 2H, 4H, 1D, and 1W. Use <b>Lookback</b> to change the number of requested bars.",
])
h2("Customize the chart session")
p("Open <b>Customize Bar</b> beside the timeframe and lookback controls. Enter a bar amount and choose a unit (Current "
  "interval, Minutes, Hours, or Monthly); choose a session, then click <b>Apply</b>. The session choices are All SIP "
  "hours, Premarket 4:00–9:30 a.m. ET, Regular 9:30 a.m.–4:00 p.m. ET, and Extended 4:00 a.m.–8:00 p.m. ET (all times "
  "are Eastern). Session selection recalculates intraday OHLC and volume from available trades. Daily and weekly bars "
  "use their own full-period aggregation. Tick, volume, and range bar builders are not in the current customize "
  "control.")
h2("Current tabs")
p("Welcome · Command Center · Sigma Radar · Live Opportunity Center · Sigma Analysis · Heat Map · Broker Behavioral "
  "Intelligence · Behavioral Intelligence · Import History · Journal · Portfolio · Preferences · Reports · Morning "
  "Report · Billing · User Guide · Admin. The Admin tab holds restricted controls; the subscriber procedures below do "
  "not require those controls.")

# ───────────────────────────── chapter 3 ─────────────────────────────
h1("Chapter 3 — Your Daily and Weekly Routine", break_before=True)
p("A consistent review sequence helps you move from broad discovery to a single symbol, then back to your own "
  "decisions. Use the schedule below as a practical example and adjust it for the hours and markets you follow.")
h2("A typical daily routine")
h3("Before the session")
bullets([
    "Open <b>Morning Report</b> and press <b>Play</b> when a report is available. Pause, resume, stop, or step between "
    "sentences as needed. Check <b>Reports</b> for the latest saved nightly analysis and its date.",
    "Review <b>Sigma Radar</b> for the latest scan timestamp. Filter by signal type, sort the results, and open a chart "
    "by selecting a row. A missing result may simply mean the selected scan found no matching pattern.",
    "Use <b>Live Opportunity Center</b> to review the watchlist, qualifying opportunities, and lifecycle strip. Select "
    "a row to load the linked three-chart workspace and read its detail panel.",
])
h3("During the session")
bullets([
    "Load the chosen symbol in <b>Command Center</b>. Compare the quote area, live price, candlesticks, volume, chart "
    "history, and price ladder. Check the chart session and timestamp when extended-hours or premarket data matters.",
    "Read <b>Sigma Analysis</b> for independent time-bar, Renko, point-and-figure, and Wyckoff readings. Use <b>Heat "
    "Map</b> to inspect sector and industry performance in its hourly, daily, weekly, or monthly view.",
    "If you make a trading decision, record the plan with <b>Save Plan</b> and the entry through <b>Enter Trade</b> or "
    "the <b>Journal</b> entry form, as appropriate. These controls record your decisions in Sigmalytic; they do not "
    "submit broker orders.",
])
h3("After the session")
bullets([
    "Close and review trades in <b>Journal</b>. Inspect <b>Portfolio</b> for open positions, live P&amp;L, allocation, "
    "and sector exposure. Check <b>Behavioral Intelligence</b> for execution, discipline, timing, and risk patterns.",
    "Compare the session’s decisions against the entry, stop, target, and notes you recorded. Read the latest report "
    "rather than assuming an older report reflects the current session.",
])
h2("A typical weekly routine")
bullets([
    "Import a new brokerage CSV in <b>Import History</b> if you want past trades included. Check the upload status and "
    "import summary before relying on the resulting behavioral profile.",
    "In <b>Preferences</b>, choose alert delivery, watchlist, market-hours suppression, and whether the nightly report "
    "should be emailed when saved. The report email choice is separate from the alert delivery frequency.",
    "If a broker or advisor manages an account for you, upload its latest statements to a vault in <b>Broker Behavioral "
    "Intelligence</b> and compare the grade, the benchmark result, and the fees with your last review.",
    "Compare your completed trades with the regime and behavior views in Behavioral Intelligence. Focus on repeat "
    "patterns rather than drawing a conclusion from one trade.",
    "Revisit the watchlist and Portfolio together: a chart opportunity and an existing position may concentrate exposure "
    "in the same symbol or sector.",
])

# ───────────────────────────── chapter 4 ─────────────────────────────
h1("Chapter 4 — Core Concepts", break_before=True)
p("The sections below follow the current tab bar. A label such as “loading,” “insufficient history,” or “no patterns "
  "found” describes the data available at that moment; it is not a trade conclusion.")

sec("4.1 Welcome")
p("The opening page includes the founder’s foreword and explains the app, Behavioral Intelligence, reports, alerts, and "
  "how to share feedback. <b>Open User Guide</b> opens this guide. Its copyright notice identifies the company’s "
  "protected application and content.")

sec("4.2 Command Center")
h3("Live quote and Smart Chart")
p("Use the symbol field, <b>Load Symbol</b>, timeframe buttons, <b>Lookback</b>, and <b>Customize Bar</b> above the "
  "tabs. The live price tile and chart follow the selected ticker; the quote area shows bid, last trade, ask, and "
  "their available timestamps. The <b>Smart Chart</b> is the main chart of this tab: OHLC candlesticks with separate "
  "regular and cumulative volume views, optional annotation overlays, and the live price. Its live price and current "
  "bar update as fresh market data arrives. The chart gives its own no-bar message if that symbol, session, or "
  "interval has no returned history.")
p("The chart fits the available viewport. Its chart-history control lets you browse earlier candles; you can zoom or "
  "reset zoom. In the volume ladders, drag or scroll over the scale to adjust the visible height of regular and "
  "cumulative volume. Annotation checkboxes control wave and structure overlays. <b>Vibration (% reversal)</b> is the "
  "percentage price reversal that ends one wave and starts the next; a smaller value marks more, shorter waves. "
  "<b>Vibration selection</b> offers Empirical Auto, in which the platform sets the percentage from that symbol’s own "
  "price history (<b>Calibrate from History</b> repeats this), or Manual Override, in which you enter the percentage. "
  "The <b>Daily volume MA period</b> and the optional Call Wall, Put Wall, and Gamma Flip Point inputs also change "
  "what you see. <b>Generate Report</b> summarizes the chart’s current analysis. Manual wall levels and synthetic "
  "fallback must not be mistaken for a verified live options chain; read the options-data label.")
h3("Decision and trade panels")
p("The <b>Price Ladder</b> lists the live price together with the platform’s reference levels around it (breakout, "
  "liquidity, expansion, trigger, trap door, and fail gate), each with its distance from the live price and risk/reward "
  "context. Additional cards show decision and structural information, including separate Renko-Weis and PnF-Weis "
  "readings when data is available. The <b>Plan Trade</b> panel accepts direction, entry, stop, target, size, and setup "
  "notes. <b>Save Plan</b> records intention; <b>Enter Trade</b> records an entry for behavioral tracking. Use the "
  "active-trade and Journal controls to review and close positions you recorded. These are recordkeeping actions, not "
  "brokerage execution.")

sec("4.3 Sigma Radar")
p("Sigma Radar displays the most recent Russell 1000 structural scan with a last-run timestamp and scanned/hit counts. "
  "Results appear in three tables: “Trades about to happen — sequential Weis setups,” “Armed trade setups,” and “All "
  "validated Spring (Bear Trap) and Upthrust (Bull Trap) events.” Use <b>Filter</b> to select a signal type and "
  "<b>Sort</b> to order hits (Most Patterns, Newest Alert First, Oldest Alert First, or Symbol (A-Z)). Click a result "
  "row to open that symbol’s chart. The result chart has its own timeframe, lookback, and volume moving-average "
  "controls. Inside the chart are the annotation layers, candlesticks, volume views, and volume-scale interaction. "
  "<b>Close Chart</b> hides the selected chart. Scan settings and <b>Run Scan Now</b> are administrator controls and "
  "do not appear for a normal subscriber.")
p("The signal filter offers eleven choices: Spring (Bear Trap), Upthrust (Bull Trap), Buying Climax, Selling Climax, "
  "3-Bar Reversal, Absorption / No Supply, Distribution / No Demand, Sign of Strength, Sign of Weakness, Breakout, and "
  "Breakdown. A Spring (Bear Trap) is a failed break below support; an Upthrust (Bull Trap) is a failed break above "
  "resistance.")
p("The first two tables list setups that are forming or armed; the last table lists historical detections. In every "
  "table, a row is a candidate to study, not an instruction to trade or proof that the setup remains active right now. "
  "Compare it with current price and volume first.")

sec("4.4 Live Opportunity Center")
p("This tab starts with a watchlist radar, scan metadata, a lifecycle strip, a paginated table of qualifying symbols, "
  "and a selected-symbol detail panel. The <b>lifecycle strip</b> is a row of five counters showing how many "
  "opportunities are at each stage: Building (early development), Armed (conditions met), Triggered (event detected), "
  "Confirmed (follow-through), and Invalidated (setup failed). Click <b>Refresh Opportunities</b> to request the latest "
  "snapshot. Click any table row to populate the three-chart workspace. The <b>Previous</b> and <b>Next</b> buttons "
  "page through the qualifying universe.")
p("The workspace can show one symbol at three timeframes or different symbols together. Choose Alert View, Structure "
  "View, Long View, Compare Symbols, or Custom. The LINKED/UNLINKED control decides whether symbol choices move "
  "together; individual chart selectors let you change symbols and timeframes. Compare the row’s alert and lifecycle "
  "information against actual price and volume before creating a plan.")

sec("4.5 Sigma Analysis")
p("For the loaded ticker, Sigma Analysis presents four separate reads: Time-Bar Weis Engine, Renko-Weis Engine, "
  "PnF-Weis Engine, and Wyckoff structure. The analysis tab uses the Sigma name, while its individual engine cards "
  "retain their Weis labels. A cross-engine synthesis explains agreements or differences without averaging the engines "
  "into a single grade. Read each engine’s status and available wave, brick, column, effort vs. result, and "
  "directional text. A PnF count guide may show a measured cause and possible effect targets when enough data exists. "
  "An unavailable or insufficient-history state means that particular engine cannot provide a current reading.")

sec("4.6 Heat Map")
p("The Sector / Industry Heat Map groups Russell 1000 symbols by sector and industry. Tile color represents price "
  "performance and tile size represents trading volume. Select Hourly, Daily, Weekly, or Monthly to change the period; "
  "use it to see where broad participation is strengthening or weakening, then study a specific symbol elsewhere in "
  "the app.")

sec("4.7 Broker Behavioral Intelligence")
p("This tab grades a broker, advisor, or fund manager the same way Behavioral Intelligence grades you. It holds five "
  "<b>vaults</b>, one for each account you want to review. Each vault keeps every statement you upload for that "
  "account, so the grade builds up over time and the five grades can be compared side by side.")
bullets([
    "Give the vault an account name and a broker or advisor name, then click <b>Save labels</b>.",
    "Choose <b>Transactions (buys and sells)</b> or <b>Holdings (positions and cash)</b>, then drag a CSV onto the "
    "upload box or click to browse. Add as many statements as you like; the same trade uploaded twice in overlapping "
    "exports is counted once.",
    "Click <b>View review</b> to open the full review under the vault cards. <b>Empty vault</b> deletes every statement "
    "in that vault after a confirmation.",
])
p("A transactions file grades how the account was traded. A holdings file adds portfolio health, cash, and benchmark "
  "comparison. The review shows:")
bullets([
    "An overall A–F grade, plus separate A–F grades for Execution, Discipline, Timing, and Risk Management, each with "
    "the evidence behind it. A vault needs at least five completed trades to be graded.",
    "Behavior flags, such as quick re-entry after a loss, and the results of the completed trades.",
    "Portfolio health: concentration, effective number of independent holdings, sector weights, and cash.",
    "A comparison with the Russell 1000, using the IWB fund as the benchmark, with the value the account added or lost "
    "after fees and the maximum drawdown of each.",
    "Fees and costs, cash (protective when the market fell, unproductive when it rose), and the mix of short-term and "
    "long-term results.",
    "Every buy or sell of a Russell 1000 stock, with its sector and Sigmalytic’s reading as of the trade date, using "
    "only price history up to that day. Each trade carries one of three labels: “with the setup,” “against the setup,” "
    "or “no confirmed setup.”",
])
p("Any section that the uploaded statements cannot support says <b>Not enough data</b> and gives the reason; "
  "Sigmalytic does not guess. For example, cash and portfolio health need a holdings file, and fees need a fee or "
  "commission column. You must be signed in to use vaults; the demo account cannot store statements. A grade "
  "evaluates the decisions documented in the statements. It is not investment advice and does not by itself show that "
  "a broker acted improperly. Compare vaults over the same period.")

sec("4.8 Behavioral Intelligence")
p("The Behavioral Profile displays total trades, a composite decision score, and separate Execution, Discipline, "
  "Timing, and Risk Management scores. Other panels show warnings and the most common behavior pattern, best and worst "
  "regime where available, a regime-performance table, and recent trade scorecards. These readings depend on recorded "
  "or imported trading history. With little history, empty or insufficient-data states are expected.")
p("Use the profile to compare what you planned with what you recorded, and to spot repeatable habits. A behavioral "
  "grade evaluates documented decisions; it is distinct from a symbol’s market-structure reading.")

sec("4.9 Import History")
p("Export a brokerage trade-history CSV, then drag it to <b>Upload Brokerage Statement</b> or click to browse. The "
  "screen lists export guidance and supported broker or generic CSV formats. Read the upload status and "
  "reconstructed-history summary, then inspect Behavioral Intelligence to see the resulting profile.")

sec("4.10 Journal")
p("The Journal offers three forms, a list of open and closed trades, and a Trader Behavioral Profile view.")
bullets([
    "<b>Log New Trade</b> (button: <b>Log Trade Entry</b>): enter the symbol, direction, entry date, entry price, and "
    "shares. Portfolio Value, Stop Loss, Tier, and Notes are also available.",
    "<b>Close / Exit Open Trade</b> (button: <b>Close / Exit Trade</b>): choose an open trade, then enter the exit date, "
    "exit price, exit reason, and exit notes.",
    "<b>Edit Journal Entry</b> (button: <b>Save Changes</b>): choose an entry and correct its symbol, direction, entry "
    "date, entry price, shares, stop loss, or notes. Fields you leave blank are not changed.",
])
p("Check the displayed status after each submission. Journal records feed behavioral review and the Portfolio summary; "
  "they are not orders at a broker.")

sec("4.11 Portfolio")
p("Portfolio summarizes Open Positions, Capital Deployed, and average Unrealized P&amp;L. The open-positions table "
  "shows symbol, direction, entry, current price, P&amp;L, allocation, and sector; a sector-exposure panel groups "
  "capital by sector. Allocation is shown as a percentage of the Portfolio Value you set in Preferences. If there are "
  "no open positions, log a trade in Journal to populate the page. P&amp;L depends on available current prices and the "
  "position details you recorded.")

sec("4.12 Preferences")
p("Choose Real-time, Hourly Digest, or Daily Summary for alerts. Set the <b>Minimum Confluence Score</b> with the "
  "slider (0 to 100, in steps of 5) and click <b>Save Score</b>; a higher minimum sends fewer alerts. Toggle Structure "
  "Alerts, Vector Alerts, Score Alerts, Cycle Alerts, and Level Alerts (described below), and maintain a watchlist of "
  "symbols (empty means all). <b>Market hours only</b> suppresses alerts outside 9:30 a.m.–4:00 p.m. Eastern. Enter "
  "your total account value under <b>Portfolio Value</b> and click <b>Save</b>; the Portfolio tab uses it for its "
  "allocation column. Choose a Hurst Cycle Profile (Short, 90 days; Medium, 1 year; or Long, 3 years). Set Weis Wave "
  "Sensitivity with the slider (lower values are more sensitive) and click <b>Save Sensitivity</b>.")
p("The five alert types are optional categories, each based on a different part of Sigmalytic’s analysis:")
bullets([
    "<b>Structure Alerts</b> — alerts based on Wyckoff market-structure patterns.",
    "<b>Vector Alerts</b> — alerts that include angle-based reference price levels for the symbol.",
    "<b>Score Alerts</b> — alerts based on the platform’s overall score for a symbol.",
    "<b>Cycle Alerts</b> — alerts based on the platform’s wave-count read of a symbol.",
    "<b>Level Alerts</b> — alerts based on proportional price levels measured from recent swings.",
])
p("A new account starts with Real-time delivery, a minimum score of 60, Market hours only on, and Structure, Vector, "
  "and Score Alerts on; Cycle and Level Alerts start off.")
p("The separate Daily Intelligence Report card asks, “Email me the nightly report when it is saved?” Choose <b>Yes</b> "
  "to receive the report by email when it is saved; choose <b>No</b> to stop. The buttons are unavailable if your "
  "account preference cannot be read. This choice does not change alert frequency. Read the status shown after "
  "changing a setting.")

sec("4.13 Reports")
p("Reports lists saved nightly intelligence reports. Choose a date to read the saved report in the in-app preview; use "
  "<b>Download PDF</b> or <b>Print / Save PDF</b> for a copy. An empty list means no stored report was returned or the "
  "archive could not be reached. Report generation and deletion buttons, when present, are administrator actions. The "
  "email option for new nightly reports lives in Preferences.")

sec("4.14 Morning Report")
p("The Morning Report tab reads the saved morning text aloud through your browser’s speech synthesis. Press "
  "<b>Play</b>; use <b>Pause / Resume</b>, <b>Stop</b>, <b>Previous</b>, and <b>Next</b>. Previous and Next move by "
  "sentence, rather than by seconds, because this is spoken text and not a recorded audio file. The currently spoken "
  "sentence is highlighted in the text panel. Playback needs a saved report and browser speech support.")

sec("4.15 Billing")
p("Billing shows a plan banner and the embedded pricing table. Choose a plan in the pricing table; payment is handled "
  "by Stripe. Read the displayed plan, price, and confirmation before making a change. If the banner does not reflect "
  "a plan you have already paid for, contact support (Chapter 6). The tab sits between Morning Report and User Guide "
  "in the tab bar.")

sec("4.16 User Guide")
p("The User Guide tab embeds this PDF and provides <b>Open Full Guide</b> and <b>Download PDF</b>. On a phone, opening "
  "the PDF in a separate view is usually easier to read. The guide describes the interface and outputs available at "
  "the edition date on the cover.")

sec("4.17 Admin")
p("The Admin tab contains operational and diagnostic controls for authorized administrators. Some other tabs expose "
  "additional manual scan, generation, or configuration controls only to an administrator. Subscribers can use the "
  "read-only results and report views described in the previous sections without running these jobs.")

# ───────────────────────────── chapter 5 ─────────────────────────────
h1("Chapter 5 — Glossary", break_before=True)
p("Terms below describe labels and views in the current platform. Interpret estimates and structural patterns as "
  "research context.")
gloss([
    ("3-Bar Reversal", "A structural scan pattern detected over three bars."),
    ("Absorption / No Supply", "Scan label for heavy volume met with little price progress, read as selling pressure "
                               "drying up."),
    ("Alert types (Structure, Vector, Score, Cycle, Level)", "Optional alert categories in Preferences, each based on "
                                                             "a different part of the platform’s analysis. See 4.12."),
    ("Alert View", "A preset of the three-chart opportunity workspace focused on alert timeframes."),
    ("Ask / Bid", "Displayed best available offer to sell / bid to buy in the quote area; these can differ from the "
                  "last traded price."),
    ("Bar / Candle", "An open, high, low, close, and volume summary over the selected timeframe and session."),
    ("Breakout / Breakdown", "Scan labels for price moving through resistance (breakout) or support (breakdown)."),
    ("Broker vault", "One of five slots in Broker Behavioral Intelligence. Each holds the statements for one account "
                     "and has its own A–F grade."),
    ("Building / Armed / Triggered / Confirmed / Invalidated", "Lifecycle stages shown in the Live Opportunity Center, "
                                                               "in order: a setup that is forming (Building), is ready "
                                                               "(Armed), has fired (Triggered), and then either has "
                                                               "followed through (Confirmed) or has failed "
                                                               "(Invalidated)."),
    ("Buying / Selling Climax", "High-activity pattern labels used in the structural scan and chart analysis; context "
                                "matters."),
    ("Call Wall / Put Wall", "Options-related price levels when a live chain supports them; the chart can also show "
                             "manual inputs or a labeled synthetic fallback."),
    ("Composite Decision Score", "Behavioral Intelligence’s overall assessment of documented trading decisions, "
                                 "distinct from a market signal."),
    ("Confluence Score", "A score from 0 to 100. In Preferences you set a minimum, and alerts are sent only at or above "
                         "it; a higher minimum means fewer alerts."),
    ("Cumulative Volume", "Chart view accumulating activity across a wave or period; its scale can be adjusted in the "
                          "chart."),
    ("Distribution / No Demand", "Scan label for the mirror case of absorption, read as buying interest fading."),
    ("Effort vs. Result", "Compares trading volume with the price movement achieved; used in the wave-analysis panels."),
    ("Extended hours", "The 4:00 a.m.–8:00 p.m. Eastern chart session choice, dependent on available SIP trades."),
    ("Fail Gate / Trap Door", "Lower structural reference levels shown on the Command Center Price Ladder."),
    ("Gamma Flip Point", "Estimated price level associated with a change in net options gamma exposure when suitable "
                         "options data exists."),
    ("Heat Map", "Treemap grouped by sector and industry; color shows performance and tile size shows volume."),
    ("Hurst Cycle Profile", "Selectable lookback horizon for the app’s cycle-timing analysis: Short (90 days), Medium "
                            "(1 year), or Long (3 years)."),
    ("Intraday", "A timeframe shorter than one trading day; session selection can change its OHLC and volume."),
    ("Last trade", "Most recently reported executed trade in the quote area, with its own timestamp."),
    ("Lifecycle strip", "The row of five counters at the top of the Live Opportunity Center showing how many "
                        "opportunities are at each lifecycle stage."),
    ("Lookback", "Requested count of historical bars; availability still depends on the data source and timeframe."),
    ("OHLC", "Open, high, low, and close prices of a chart bar."),
    ("PnF / Point and Figure", "Column-based price construction used by one of the separate Sigma Analysis engines."),
    ("Premarket", "The 4:00–9:30 a.m. Eastern intraday session choice in Customize Bar."),
    ("Price Ladder", "The Command Center list of the live price and the platform’s reference levels around it, with "
                     "distance and risk/reward context."),
    ("Protective cash / Unproductive cash", "Cash that helped because the market fell (protective), or cost return "
                                            "because the market rose (unproductive), measured against the Russell 1000 "
                                            "benchmark."),
    ("Regime", "A market-condition category used to group your trades in Behavioral Intelligence."),
    ("Regular session", "The 9:30 a.m.–4:00 p.m. Eastern intraday chart session choice."),
    ("Renko", "Price-brick representation used by a separate wave engine; it is not a time-based candle."),
    ("Risk/reward ratio", "Displayed comparison between potential gain toward a reference level and potential loss "
                          "toward a failure level."),
    ("Russell 1000", "An index of the 1,000 largest publicly traded U.S. companies by market capitalization; the "
                     "universe for Sigma Radar, Heat Map, and the Broker Behavioral Intelligence benchmark."),
    ("Sign of Strength / Sign of Weakness", "Structural scan labels for price and volume behavior that suggests rising "
                                            "demand or rising supply."),
    ("SIP", "Securities Information Processor feed referenced by the quote and chart-hours controls."),
    ("Smart Chart", "The main Command Center chart: OHLC candlesticks with regular and cumulative volume, optional "
                    "annotation overlays, and the live price."),
    ("Spring (Bear Trap) / Upthrust (Bull Trap)", "Structural scan labels for failed breaks. A Spring (Bear Trap) is a "
                                                  "failed break below support: price drops under support, then "
                                                  "recovers. An Upthrust (Bull Trap) is a failed break above "
                                                  "resistance: price pushes over resistance, then falls back."),
    ("Trades about to happen", "The Sigma Radar table of sequential Weis setups that are close to triggering; "
                               "candidates to study, not instructions."),
    ("Unrealized P&amp;L", "Open-position gain or loss based on recorded entry and a currently available market price."),
    ("Value added", "The account’s return after fees minus the benchmark’s return over the same period. Negative means "
                    "the account trailed the benchmark."),
    ("Vibration", "The percentage price reversal that ends one wave and starts the next on the Smart Chart; a smaller "
                  "value marks more, shorter waves. It can be set automatically from the symbol’s history or entered "
                  "manually."),
    ("Volume MA", "Moving average of chart-bar volume over the selected number of bars."),
    ("Wave sensitivity", "Reversal threshold used in the wave analysis setting; lower values are more sensitive."),
    ("Weis Wave", "Volume accumulated across each price wave, where a wave ends when price reverses by more than the "
                  "wave sensitivity."),
    ("With the setup / Against the setup", "Whether a Russell 1000 buy or sell agreed with a confirmed Sigmalytic setup "
                                           "on the trade date. A buy agrees with a confirmed long setup; a sell agrees "
                                           "with a confirmed short setup."),
    ("Wyckoff", "A price-and-volume market-structure framework displayed as a separate Sigma Analysis reading."),
])

# ───────────────────────────── chapter 6 ─────────────────────────────
h1("Chapter 6 — Support and Feedback", break_before=True)
h2("Contact")
p("For help, a bug report, or a suggestion, email <b>teams@sigmalyticquantcorp.com</b>. Please allow 24–48 hours for a "
  "response. Include your account email, the tab and symbol involved, when it happened, the chart timeframe and "
  "session if relevant, and a screenshot or the exact on-screen error. Never include a password in a support email.")
h2("Copyright and permitted use")
p("© 2026 Sigmalytic Quant Corporation. All rights reserved. The Sigmalytic application design, software and source "
  "code, analyses, reports, text, charts, graphics, and this guide are protected by copyright. Copying, modifying, "
  "distributing, or reusing these materials requires prior written permission, except as permitted by law or an "
  "applicable license. Third-party market data and licensed materials remain the property of their respective rights "
  "holders.")
p("This guide is provided to Sigmalytic users for using Sigmalytic and is confidential: do not share it with anyone "
  "who is not a Sigmalytic user without written permission. For reuse permissions, contact the support email above.")

# ───────────────────────────── appendix ─────────────────────────────
h1("Appendix A — Worked Examples", break_before=True)


def example(title, items):
    h2(title)
    bullets(items)


example("Example 1 — Compare an opportunity against live price and volume", [
    "Open Live Opportunity Center, review its snapshot timestamp, select a qualifying symbol, and read its detail panel "
    "and three charts.",
    "Type that symbol in the header and click <b>Load Symbol</b>. Open Command Center and compare bid, last, ask, live "
    "price, candles, regular volume, and cumulative volume.",
    "Choose the desired timeframe and Customize Bar session. Review the Price Ladder and the source label for options "
    "levels before saving a plan.",
])
example("Example 2 — Read a structural pattern in Sigma Radar", [
    "Open Sigma Radar, read the last-run time, filter for a pattern, and sort the matches. Click one row.",
    "Choose the chart timeframe, lookback, and volume MA. Adjust volume-ladder scale if needed; turn annotation layers "
    "on only when they help interpret the bars.",
    "Cross-check the symbol in Sigma Analysis. Treat a pattern hit and a wave-engine disagreement as information to "
    "investigate, not as an automatic entry.",
])
example("Example 3 — Study premarket and regular-session candles", [
    "Load a symbol and select an intraday timeframe, such as 5m. Open Customize Bar, choose Premarket 4:00–9:30 a.m. ET, "
    "and click <b>Apply</b>.",
    "Note the timestamps, open/high/low/close, and volume. Switch to Regular 9:30 a.m.–4:00 p.m. ET and apply again to "
    "compare the regular session. Use All SIP hours or Extended when a broader view is needed.",
    "If the selected interval returns no bars, adjust the session, timeframe, or lookback and check whether the source "
    "has historical data for those hours.",
])
example("Example 4 — Record and review a decision", [
    "In Command Center, enter direction, entry, stop, target, size, and setup notes; click <b>Save Plan</b>. When you "
    "actually enter a trade, click <b>Enter Trade</b> or log it in Journal.",
    "When you close it, use the Journal Close / Exit Open Trade form. Inspect the completed record and then open "
    "Behavioral Intelligence to review your pattern and component scores.",
    "Open Portfolio to verify that only current open positions remain. An imported broker CSV can add past records "
    "through Import History.",
])
example("Example 5 — Set up reports and alerts", [
    "In Preferences, choose alert frequency and types, set a score threshold, and add symbols to the watchlist if you "
    "only want those symbols considered for alerts.",
    "Under Daily Intelligence Report, choose <b>Yes</b> if you want a nightly report emailed when saved. Open Reports to "
    "read archived dates and download a PDF.",
    "Use Morning Report to play the current saved text. Use Previous and Next to move between sentences; there is no "
    "time-based seek control.",
])
example("Example 6 — Rebuild context from prior trades", [
    "Export transaction history from a supported broker as CSV. Open Import History, use the broker-specific export "
    "guidance, and upload a single CSV file.",
    "Read the upload result and the displayed reconstructed-history summary. If the file is rejected or has unexpected "
    "totals, check the broker export format and date range before trying again.",
    "Open Behavioral Intelligence and compare its total trades and regime table with your earlier view. The score and "
    "common-pattern panels depend on the history successfully recorded.",
])
example("Example 7 — Compare market breadth with current exposure", [
    "Choose Weekly on the Heat Map to see which sectors and industries have moved over the broader period. Compare it "
    "with Daily to see whether the recent move is similar.",
    "Open Portfolio and read the sector-exposure bars and open-positions table. Note whether several recorded positions "
    "are already in the same sector that caught your eye in the heat map.",
    "If a symbol merits individual study, enter it in the header and load Command Center. The heat map gives context; "
    "the chart, volume, and your position details provide a closer view.",
])
example("Example 8 — Check a missing or unexpected chart value", [
    "Confirm the loaded symbol, the selected timeframe, Lookback, and Customize Bar session. A premarket-only intraday "
    "chart may have no historical bars outside those hours.",
    "Read the quote receipt time and last-trade time, then compare them with the chart’s latest bar time. Bid and ask "
    "can update even when there has been no new trade or completed bar.",
    "If the mismatch persists, capture a screenshot showing the quote, live price, chart, symbol, timeframe, and "
    "session. Send it with the time and your account email to teams@sigmalyticquantcorp.com.",
])
example("Example 9 — Review a broker’s record", [
    "Open Broker Behavioral Intelligence. In Vault 1, enter the account name and the broker or advisor, and click "
    "<b>Save labels</b>.",
    "Choose Transactions, upload the broker’s transaction CSV, and repeat for each earlier statement. Choose Holdings "
    "and upload the latest positions file to unlock portfolio health, cash, and the benchmark comparison.",
    "Click <b>View review</b>. Read the overall grade and the four component grades, then the benchmark and fee "
    "sections. Note any section marked Not enough data and what file it needs.",
    "Open the Russell 1000 trades table. Look for buys and sells that went against a confirmed setup, and use them, with "
    "the flags and fees, to prepare questions for the broker.",
])


def build(path: str = OUT) -> str:
    doc = Doc(path)
    doc.multiBuild(list(story))
    return path


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else OUT))
