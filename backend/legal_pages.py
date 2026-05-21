"""
backend/legal_pages.py
----------------------
Sigmalytic Legal Pages — Privacy Policy + Terms of Service
Served directly from FastAPI backend.
Register in main.py:
    from legal_pages import legal_router
    app.include_router(legal_router)

URLs:
    GET /privacy   — Privacy Policy
    GET /terms     — Terms of Service
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

legal_router = APIRouter(tags=["legal"])

COMPANY   = "Sigmalytic Quant Corporation"
DOMAIN    = "sigmalyticquantcorp.com"
EMAIL     = "greg.kosmala@gmail.com"
APP_URL   = "https://sigmalytic-frontend.onrender.com"
EFFECTIVE = "May 21, 2026"

# ── Shared styles ──────────────────────────────────────────────────────────

CSS = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0a0f1a;
  color: #c8d8e8;
  font-family: 'Helvetica Neue', Arial, sans-serif;
  font-size: 15px;
  line-height: 1.75;
  padding: 0 16px 60px;
}
.wrap {
  max-width: 780px;
  margin: 0 auto;
  padding-top: 48px;
}
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 40px;
}
.logo-sigma {
  font-size: 32px;
  font-weight: 900;
  color: #00c896;
  line-height: 1;
}
.logo-name {
  font-size: 16px;
  font-weight: 800;
  color: #f0f4ff;
  letter-spacing: .06em;
}
.logo-sub {
  font-size: 9px;
  color: #00c896;
  letter-spacing: .22em;
  display: block;
  margin-top: 2px;
}
h1 {
  font-size: 32px;
  font-weight: 900;
  color: #f0f4ff;
  margin-bottom: 8px;
  letter-spacing: -.01em;
}
.effective {
  font-size: 12px;
  color: #5a7a8a;
  margin-bottom: 36px;
  letter-spacing: .04em;
}
h2 {
  font-size: 17px;
  font-weight: 800;
  color: #00c896;
  margin: 36px 0 10px;
  letter-spacing: .02em;
  text-transform: uppercase;
}
h3 {
  font-size: 14px;
  font-weight: 700;
  color: #f0f4ff;
  margin: 20px 0 6px;
}
p {
  margin-bottom: 14px;
  color: #b0c4d4;
}
ul {
  margin: 8px 0 14px 20px;
  color: #b0c4d4;
}
li {
  margin-bottom: 6px;
}
a {
  color: #00c896;
  text-decoration: none;
}
a:hover {
  text-decoration: underline;
}
.highlight {
  background: rgba(0,200,150,.08);
  border: 1px solid rgba(0,200,150,.25);
  border-radius: 10px;
  padding: 16px 20px;
  margin: 20px 0;
  color: #c8e8d8;
  font-size: 14px;
}
.divider {
  border: none;
  height: 1px;
  background: rgba(255,255,255,.07);
  margin: 40px 0;
}
.footer {
  margin-top: 48px;
  padding-top: 24px;
  border-top: 1px solid rgba(255,255,255,.07);
  font-size: 12px;
  color: #3a5a6a;
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.nav-links {
  margin-bottom: 32px;
  font-size: 13px;
}
.nav-links a {
  margin-right: 20px;
  color: #5a8a7a;
}
</style>
"""

def _header(title):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — {COMPANY}</title>
{CSS}
</head>
<body>
<div class="wrap">
  <div class="logo">
    <div class="logo-sigma">Σ</div>
    <div>
      <div class="logo-name">SIGMALYTIC</div>
      <span class="logo-sub">QUANT CORPORATION</span>
    </div>
  </div>
  <div class="nav-links">
    <a href="{APP_URL}">← Back to App</a>
    <a href="/privacy">Privacy Policy</a>
    <a href="/terms">Terms of Service</a>
  </div>
"""

def _footer():
    return f"""
  <div class="footer">
    <span>© {COMPANY} 2026. All rights reserved.</span>
    <span><a href="mailto:{EMAIL}">{EMAIL}</a></span>
  </div>
</div>
</body>
</html>"""


# ════════════════════════════════════════════════════════════════
# PRIVACY POLICY
# ════════════════════════════════════════════════════════════════

PRIVACY_HTML = _header("Privacy Policy") + f"""
<h1>Privacy Policy</h1>
<p class="effective">Effective Date: {EFFECTIVE}</p>

<div class="highlight">
  This Privacy Policy describes how {COMPANY} ("Sigmalytic," "we," "us," or "our")
  collects, uses, and shares information when you use our platform at
  <a href="{APP_URL}">{APP_URL}</a> and related services (collectively, the "Service").
  By using the Service, you agree to the practices described in this policy.
</div>

<h2>1. Information We Collect</h2>

<h3>Information You Provide</h3>
<ul>
  <li><strong>Account information:</strong> When you register, we collect your email address and password (stored securely via Supabase authentication).</li>
  <li><strong>Trade history:</strong> If you upload a CSV file of your trade history, we collect and store that data to generate your behavioral analysis.</li>
  <li><strong>Communications:</strong> If you contact us by email, we retain that correspondence.</li>
</ul>

<h3>Information Collected Automatically</h3>
<ul>
  <li><strong>Usage data:</strong> We collect information about how you interact with the Service, including pages visited, features used, and time spent.</li>
  <li><strong>Device information:</strong> Browser type, operating system, and IP address.</li>
  <li><strong>Log data:</strong> Server logs including access times and error logs.</li>
</ul>

<h3>Information from Third Parties</h3>
<ul>
  <li><strong>Market data:</strong> We receive delayed market data from Alpaca Markets (15-minute delayed IEX feed) to power our scoring engine.</li>
</ul>

<h2>2. How We Use Your Information</h2>
<p>We use the information we collect to:</p>
<ul>
  <li>Provide, operate, and improve the Service</li>
  <li>Send you radar alerts, status notifications, and daily summaries via email</li>
  <li>Send you SMS alerts if you have opted in to SMS notifications (Premium tier)</li>
  <li>Analyze your uploaded trade history to generate behavioral intelligence reports</li>
  <li>Authenticate your account and maintain security</li>
  <li>Respond to your inquiries and provide customer support</li>
  <li>Comply with legal obligations</li>
  <li>Detect and prevent fraud or abuse</li>
</ul>

<h2>3. SMS Communications</h2>
<div class="highlight">
  <strong>SMS Consent and Opt-In:</strong> By creating an account and enabling SMS alerts,
  you expressly consent to receive automated text messages from {COMPANY} at the mobile
  number you provide. These messages include market alerts, radar status changes, and
  service notifications.<br><br>
  <strong>Message frequency:</strong> Message frequency varies based on market activity.
  You may receive multiple messages per day during active market hours.<br><br>
  <strong>Message and data rates may apply.</strong> Standard carrier rates apply to
  all SMS messages received.<br><br>
  <strong>To opt out:</strong> Reply STOP to any SMS message at any time to unsubscribe.
  You may also disable SMS alerts in your account settings.<br><br>
  <strong>For help:</strong> Reply HELP to any SMS message or contact us at
  <a href="mailto:{EMAIL}">{EMAIL}</a>.<br><br>
  Carriers are not liable for delayed or undelivered messages.
</div>

<h2>4. How We Share Your Information</h2>
<p>We do not sell your personal information. We may share your information with:</p>
<ul>
  <li><strong>Service providers:</strong> Third-party vendors who help us operate the Service, including:
    <ul>
      <li>Supabase (database and authentication)</li>
      <li>Resend (email delivery)</li>
      <li>Twilio (SMS delivery)</li>
      <li>Alpaca Markets (market data)</li>
      <li>Render (cloud hosting)</li>
    </ul>
  </li>
  <li><strong>Legal requirements:</strong> We may disclose information if required by law, court order, or government authority.</li>
  <li><strong>Business transfers:</strong> If we are involved in a merger, acquisition, or sale of assets, your information may be transferred as part of that transaction.</li>
  <li><strong>Protection of rights:</strong> We may share information to protect the rights, property, or safety of {COMPANY}, our users, or others.</li>
</ul>

<h2>5. Data Retention</h2>
<p>
  We retain your account information for as long as your account is active or as needed to provide the Service.
  Uploaded trade history is retained until you delete it or close your account.
  You may request deletion of your data at any time by contacting us at
  <a href="mailto:{EMAIL}">{EMAIL}</a>.
</p>

<h2>6. Data Security</h2>
<p>
  We implement industry-standard security measures to protect your information, including:
</p>
<ul>
  <li>Encrypted data transmission (HTTPS/TLS)</li>
  <li>Row-level security (RLS) on all database tables</li>
  <li>Supabase authentication with secure token management</li>
  <li>No storage of plaintext passwords</li>
</ul>
<p>
  However, no method of transmission over the internet is 100% secure.
  We cannot guarantee absolute security of your information.
</p>

<h2>7. Your Rights and Choices</h2>
<p>You have the right to:</p>
<ul>
  <li><strong>Access:</strong> Request a copy of the personal information we hold about you</li>
  <li><strong>Correction:</strong> Request correction of inaccurate information</li>
  <li><strong>Deletion:</strong> Request deletion of your account and associated data</li>
  <li><strong>Opt-out of email:</strong> Unsubscribe from marketing emails at any time</li>
  <li><strong>Opt-out of SMS:</strong> Reply STOP to any SMS message at any time</li>
</ul>
<p>
  To exercise these rights, contact us at <a href="mailto:{EMAIL}">{EMAIL}</a>.
</p>

<h2>8. Children's Privacy</h2>
<p>
  The Service is not directed to individuals under the age of 18.
  We do not knowingly collect personal information from children.
  If you believe a child has provided us with personal information,
  please contact us immediately.
</p>

<h2>9. Third-Party Links</h2>
<p>
  The Service may contain links to third-party websites. We are not responsible
  for the privacy practices of those sites and encourage you to review their
  privacy policies.
</p>

<h2>10. Changes to This Policy</h2>
<p>
  We may update this Privacy Policy from time to time. We will notify you of
  material changes by posting the new policy on this page with an updated
  effective date. Your continued use of the Service after changes constitutes
  acceptance of the updated policy.
</p>

<h2>11. Contact Us</h2>
<p>
  If you have questions about this Privacy Policy, please contact us at:<br><br>
  <strong>{COMPANY}</strong><br>
  Email: <a href="mailto:{EMAIL}">{EMAIL}</a><br>
  Website: <a href="{APP_URL}">{APP_URL}</a>
</p>

""" + _footer()


# ════════════════════════════════════════════════════════════════
# TERMS OF SERVICE
# ════════════════════════════════════════════════════════════════

TERMS_HTML = _header("Terms of Service") + f"""
<h1>Terms of Service</h1>
<p class="effective">Effective Date: {EFFECTIVE}</p>

<div class="highlight">
  Please read these Terms of Service carefully before using the Sigmalytic platform.
  By accessing or using our Service, you agree to be bound by these terms.
  If you do not agree, do not use the Service.
</div>

<h2>1. Acceptance of Terms</h2>
<p>
  These Terms of Service ("Terms") constitute a legally binding agreement between you
  and {COMPANY} ("Sigmalytic," "we," "us," or "our") governing your use of the
  Sigmalytic platform and all related services (the "Service").
</p>

<h2>2. Description of Service</h2>
<p>
  Sigmalytic is a behavioral decision intelligence platform that provides:
</p>
<ul>
  <li>Real-time market scoring and analysis across 1,400+ symbols</li>
  <li>Radar alerts for Armed, Triggered, and other market status changes</li>
  <li>Email and SMS notifications for market events</li>
  <li>Behavioral intelligence analysis of uploaded trade history</li>
  <li>Signal scoreboard tracking historical performance</li>
  <li>Market regime detection and projection paths</li>
</ul>

<div class="highlight">
  <strong>⚠️ Important Disclaimer:</strong> Sigmalytic provides market intelligence
  and informational content only. Nothing on the Service constitutes financial advice,
  investment advice, trading advice, or any other type of professional advice.
  All market data is 15-minute delayed. Past performance does not guarantee future results.
  You are solely responsible for your own investment decisions.
</div>

<h2>3. Eligibility</h2>
<p>To use the Service, you must:</p>
<ul>
  <li>Be at least 18 years of age</li>
  <li>Be a resident of the United States</li>
  <li>Have the legal capacity to enter into a binding agreement</li>
  <li>Not be prohibited from using the Service under applicable law</li>
</ul>

<h2>4. Account Registration</h2>
<p>
  To access certain features, you must create an account. You agree to:
</p>
<ul>
  <li>Provide accurate and complete registration information</li>
  <li>Maintain the security of your password</li>
  <li>Notify us immediately of any unauthorized access to your account</li>
  <li>Accept responsibility for all activity under your account</li>
</ul>
<p>
  We reserve the right to suspend or terminate accounts that violate these Terms.
</p>

<h2>5. SMS Terms and Conditions</h2>
<div class="highlight">
  <strong>Program Description:</strong> By opting in to SMS alerts, you agree to receive
  automated text messages from {COMPANY} regarding market radar alerts, status changes,
  and service notifications.<br><br>
  <strong>Sender:</strong> Messages will be sent from Sigmalytic Quant Corporation
  via our toll-free number.<br><br>
  <strong>Message Frequency:</strong> Message frequency varies. You may receive
  multiple messages per trading day based on market activity.<br><br>
  <strong>Cost:</strong> Message and data rates may apply. Contact your wireless
  provider for details.<br><br>
  <strong>Opt-Out:</strong> To stop receiving SMS messages, reply STOP to any message.
  You will receive a confirmation and no further messages will be sent.<br><br>
  <strong>Help:</strong> Reply HELP for assistance or contact
  <a href="mailto:{EMAIL}">{EMAIL}</a>.<br><br>
  <strong>Carriers:</strong> Supported carriers include but are not limited to:
  AT&T, Verizon, T-Mobile, Sprint, Boost Mobile, MetroPCS, U.S. Cellular.
  Carriers are not liable for delayed or undelivered messages.<br><br>
  <strong>Privacy:</strong> Your information will not be shared with third parties
  for marketing purposes. See our <a href="/privacy">Privacy Policy</a> for details.
</div>

<h2>6. Subscription and Payment</h2>
<h3>Free Tier</h3>
<p>
  The Service offers a free tier with limited features including access to the radar
  screen, basic alerts, and the signal scoreboard. No payment information is required
  for the free tier.
</p>
<h3>Premium Tier</h3>
<p>
  Premium subscriptions provide access to additional features including live data feeds,
  expanded symbol universe, SMS alerts, and behavioral intelligence tools. Premium
  pricing is displayed at the time of subscription. All fees are in US dollars.
</p>
<h3>Cancellation</h3>
<p>
  You may cancel your subscription at any time. Cancellation takes effect at the end
  of your current billing period. No refunds are provided for partial periods.
</p>

<h2>7. Acceptable Use</h2>
<p>You agree not to:</p>
<ul>
  <li>Use the Service for any unlawful purpose</li>
  <li>Attempt to reverse engineer, scrape, or copy our scoring algorithms or data</li>
  <li>Share your account credentials with others</li>
  <li>Use automated bots or scripts to access the Service</li>
  <li>Interfere with or disrupt the Service or its servers</li>
  <li>Resell or redistribute our market intelligence or alert data</li>
  <li>Use the Service to manipulate markets or engage in fraudulent trading</li>
</ul>

<h2>8. Intellectual Property</h2>
<p>
  The Service and all content, features, and functionality — including but not limited to
  the Confluence Engine™, Expansion Node Modeling™, Forward Projection Layer™, scoring
  algorithms, and software — are owned by {COMPANY} and protected by intellectual
  property laws. You may not copy, modify, distribute, or create derivative works
  without our express written consent.
</p>

<h2>9. Market Data and Disclaimers</h2>
<ul>
  <li>All market data provided through the Service is for informational purposes only</li>
  <li>Market data is delayed by 15 minutes via the Alpaca IEX free feed</li>
  <li>We make no representations about the accuracy or completeness of market data</li>
  <li>Sigmalytic is not a registered investment advisor, broker-dealer, or financial planner</li>
  <li>Nothing in the Service constitutes a recommendation to buy or sell any security</li>
  <li>Past performance of our scoring system does not guarantee future results</li>
</ul>

<h2>10. Limitation of Liability</h2>
<p>
  TO THE MAXIMUM EXTENT PERMITTED BY LAW, {COMPANY.upper()} SHALL NOT BE LIABLE FOR
  ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING
  BUT NOT LIMITED TO LOSS OF PROFITS, DATA, OR TRADING LOSSES, ARISING OUT OF OR
  RELATED TO YOUR USE OF THE SERVICE, EVEN IF WE HAVE BEEN ADVISED OF THE POSSIBILITY
  OF SUCH DAMAGES.
</p>
<p>
  OUR TOTAL LIABILITY TO YOU FOR ALL CLAIMS ARISING OUT OF OR RELATED TO THE SERVICE
  SHALL NOT EXCEED THE AMOUNT YOU PAID TO US IN THE TWELVE MONTHS PRECEDING THE CLAIM,
  OR $100, WHICHEVER IS GREATER.
</p>

<h2>11. Indemnification</h2>
<p>
  You agree to indemnify and hold harmless {COMPANY}, its officers, directors, employees,
  and agents from any claims, damages, losses, or expenses (including reasonable attorneys'
  fees) arising out of your use of the Service, violation of these Terms, or infringement
  of any third-party rights.
</p>

<h2>12. Disclaimer of Warranties</h2>
<p>
  THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND,
  EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF
  MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT. WE DO NOT
  WARRANT THAT THE SERVICE WILL BE UNINTERRUPTED, ERROR-FREE, OR THAT DEFECTS WILL
  BE CORRECTED.
</p>

<h2>13. Governing Law</h2>
<p>
  These Terms shall be governed by and construed in accordance with the laws of the
  United States, without regard to conflict of law principles. Any disputes shall be
  resolved in the applicable courts of the United States.
</p>

<h2>14. Changes to Terms</h2>
<p>
  We reserve the right to modify these Terms at any time. We will notify users of
  material changes by posting the updated Terms with a new effective date. Your
  continued use of the Service after changes constitutes acceptance.
</p>

<h2>15. Termination</h2>
<p>
  We reserve the right to suspend or terminate your access to the Service at any time,
  with or without cause, with or without notice. Upon termination, your right to use
  the Service ceases immediately.
</p>

<h2>16. Contact Us</h2>
<p>
  If you have questions about these Terms, please contact us at:<br><br>
  <strong>{COMPANY}</strong><br>
  Email: <a href="mailto:{EMAIL}">{EMAIL}</a><br>
  Website: <a href="{APP_URL}">{APP_URL}</a>
</p>

""" + _footer()


# ── Routes ─────────────────────────────────────────────────────────────────

@legal_router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    """Privacy Policy page — required for Twilio SMS compliance."""
    return HTMLResponse(content=PRIVACY_HTML)


@legal_router.get("/terms", response_class=HTMLResponse)
async def terms_of_service():
    """Terms of Service page — required for Twilio SMS compliance."""
    return HTMLResponse(content=TERMS_HTML)
