from datetime import date
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="Global Income Tax Estimator", page_icon=None, layout="wide"
)

st.title("Global Foreign Ordinary Income Tax Estimator")
st.markdown(
    "Calculate precise cross-border ordinary income tax liabilities, apply"
    " Foreign Tax Credits (FTC), and model tax burdens using India's New Tax"
    " Regime (with marginal relief) and global jurisdictions."
)

st.warning(
    "Disclaimer: This application is provided for informational and estimation"
    " purposes only and does not constitute formal legal or tax advice. Please"
    " consult a qualified tax professional for official tax filings."
)

# -----------------------------------------------------------------------------
# 1. HISTORICAL & LIVE EXCHANGE RATE ENGINE
# -----------------------------------------------------------------------------


@st.cache_data(ttl=3600)
def fetch_exchange_rate(base: str, target: str, rate_date: str = None):
  usd_rates = {
      "USD": 1.0,
      "INR": 83.5,
      "GBP": 0.79,
      "EUR": 0.92,
      "JPY": 155.0,
      "CAD": 1.36,
      "AUD": 1.52,
  }

  try:
    if rate_date:
      url = (
          f"https://api.frankfurter.dev/v1/{rate_date}?base={base}&symbols={target}"
      )
    else:
      url = f"https://api.frankfurter.dev/v1/latest?base={base}&symbols={target}"

    res = requests.get(url, timeout=3)
    if res.status_code == 200:
      data = res.json()
      rate = data["rates"].get(target)
      if rate:
        return float(rate), False
  except Exception:
    pass

  base_to_usd = 1.0 / usd_rates.get(base, 1.0)
  usd_to_target = usd_rates.get(target, 1.0)
  return (base_to_usd * usd_to_target), True


# -----------------------------------------------------------------------------
# 2. ORDINARY INCOME TAX ENGINES
# -----------------------------------------------------------------------------


# --- India New Tax Regime Engine (with Section 87A Rebate & Marginal Relief) ---
def compute_india_tax(income: float) -> float:
  taxable = max(0.0, income - 75000.0)  # ₹75,000 Standard Deduction
  base_tax = 0.0
  slabs = [
      (400000.0, 800000.0, 0.05),
      (800000.0, 1200000.0, 0.10),
      (1200000.0, 1600000.0, 0.15),
      (1600000.0, 2000000.0, 0.20),
      (2000000.0, 2400000.0, 0.25),
      (2400000.0, float("inf"), 0.30),
  ]
  for lower, upper, rate in slabs:
    if taxable > lower:
      taxable_chunk = min(taxable, upper) - lower
      base_tax += taxable_chunk * rate

  # Section 87A Rebate & Marginal Relief Logic
  if taxable <= 1200000.0:
    base_tax = 0.0
  else:
    excess_income = taxable - 1200000.0
    # Marginal relief ensures tax does not exceed income earned above ₹12 Lakhs
    if base_tax > excess_income:
      base_tax = excess_income

  # Surcharge calculation based on income tiers
  surcharge_rate = 0.0
  if taxable > 20000000.0:
    surcharge_rate = 0.25
  elif taxable > 10000000.0:
    surcharge_rate = 0.15
  elif taxable > 5000000.0:
    surcharge_rate = 0.10

  surcharge = base_tax * surcharge_rate
  tax_before_cess = base_tax + surcharge

  # Compounded 4% Health and Education Cess
  return tax_before_cess * 1.04


# --- USA Ordinary Income Engine ---
def compute_usa_tax(income: float) -> float:
  taxable = max(0.0, income - 15750.0)
  tax = 0.0
  slabs = [
      (0.0, 11925.0, 0.10),
      (11925.0, 48475.0, 0.12),
      (48475.0, 103350.0, 0.22),
      (103350.0, 197300.0, 0.24),
      (197300.0, 250525.0, 0.32),
      (250525.0, 626350.0, 0.35),
      (626350.0, float("inf"), 0.37),
  ]
  for lower, upper, rate in slabs:
    if taxable > lower:
      taxable_chunk = min(taxable, upper) - lower
      tax += taxable_chunk * rate
  return tax


# --- UK Ordinary Income Engine ---
def compute_uk_tax(income: float) -> float:
  personal_allowance = 12570.0
  if income > 100000.0:
    reduction = (income - 100000.0) / 2.0
    personal_allowance = max(0.0, personal_allowance - reduction)

  taxable = max(0.0, income - personal_allowance)
  tax = 0.0
  basic_limit = personal_allowance + 37700.0
  higher_limit = 125140.0

  if taxable > 0:
    if income <= basic_limit:
      tax += taxable * 0.20
    elif income <= higher_limit:
      tax += (37700.0) * 0.20 + (income - basic_limit) * 0.40
    else:
      tax += (
          (37700.0) * 0.20
          + (higher_limit - basic_limit) * 0.40
          + (income - higher_limit) * 0.45
      )
  return tax


# --- Germany Ordinary Income Engine ---
def compute_germany_tax(income: float) -> float:
  taxable = max(0.0, income - 11784.0)
  if taxable <= 0:
    return 0.0
  elif income <= 66760.0:
    effective_rate = 0.14 + (0.28 * (taxable / (66760.0 - 11784.0)))
    return taxable * effective_rate
  elif income <= 277825.0:
    base_tax = compute_germany_tax(66760.0)
    return base_tax + (income - 66760.0) * 0.42
  else:
    base_tax = compute_germany_tax(277825.0)
    return base_tax + (income - 277825.0) * 0.45


# --- Japan Ordinary Income Engine ---
def compute_japan_tax(income: float) -> float:
  taxable = max(0.0, income - 480000.0)
  if taxable <= 0:
    return 0.0
  slabs = [
      (1950000.0, 0.05, 0.0),
      (3300000.0, 0.10, 97500.0),
      (6950000.0, 0.20, 427500.0),
      (9000000.0, 0.23, 636000.0),
      (18000000.0, 0.33, 1536000.0),
      (40000000.0, 0.40, 2796000.0),
      (float("inf"), 0.45, 4796000.0),
  ]
  base_tax = 0.0
  for upper, rate, deduction in slabs:
    if taxable <= upper:
      base_tax = (taxable * rate) - deduction
      break
  return base_tax * 1.021


COUNTRY_ENGINES = {
    "India": {"curr": "INR", "ordinary": compute_india_tax},
    "United States": {"curr": "USD", "ordinary": compute_usa_tax},
    "United Kingdom": {"curr": "GBP", "ordinary": compute_uk_tax},
    "Germany": {"curr": "EUR", "ordinary": compute_germany_tax},
    "Japan": {"curr": "JPY", "ordinary": compute_japan_tax},
}


def render_full_metric(label: str, value_str: str):
  is_negative = value_str.strip().startswith("-")
  bg_color = "#fef2f2" if is_negative else "#f0fdf4"
  border_color = "#fecaca" if is_negative else "#bbf7d0"
  text_color = "#991b1b" if is_negative else "#166534"

  st.markdown(
      f"""
      <div style="background-color: {bg_color}; padding: 12px 16px; border-radius: 8px; border: 1px solid {border_color}; margin-bottom: 10px;">
          <div style="font-size: 13px; color: #4b5563; margin-bottom: 4px;">{label}</div>
          <div style="font-size: 18px; font-weight: 600; color: {text_color}; white-space: nowrap; overflow: visible;">{value_str}</div>
      </div>
      """,
      unsafe_allow_html=True,
  )


# -----------------------------------------------------------------------------
# 3. STREAMLIT UI
# -----------------------------------------------------------------------------

st.subheader("Foreign Income Details")
col1, col2, col3 = st.columns(3)

with col1:
  foreign_amount = st.number_input(
      "Gross Foreign Income", min_value=0.0, value=75000.0, step=5000.0
  )
with col2:
  source_curr = st.selectbox(
      "Source Currency", ["USD", "EUR", "GBP", "INR", "JPY", "CAD", "AUD"]
  )
with col3:
  foreign_tax_paid_source = st.number_input(
      f"Tax Paid at Source ({source_curr})", min_value=0.0, value=5000.0, step=500.0
  )

st.subheader("Residency Jurisdiction")
residency_choice = st.selectbox(
    "Residency Country (Tax Jurisdiction)", list(COUNTRY_ENGINES.keys())
)

target_curr = COUNTRY_ENGINES[residency_choice]["curr"]

st.subheader("Tax Year & Exchange Rate Date")
use_historical = st.checkbox(
    "Use Historical Exchange Rate (for past tax filings)"
)
rate_date_str = None

if use_historical:
  selected_date = st.date_input(
      "Select Tax Year / Filing Date",
      value=date(2025, 3, 31),
      min_value=date(2000, 1, 1),
      max_value=date.today(),
  )
  rate_date_str = selected_date.strftime("%Y-%m-%d")

if st.button("Calculate and Compare Tax Liability", type="primary"):
  rate, is_fallback = fetch_exchange_rate(
      source_curr, target_curr, rate_date=rate_date_str
  )

  local_income = foreign_amount * rate
  foreign_tax_paid_local = foreign_tax_paid_source * rate

  engine_dict = COUNTRY_ENGINES[residency_choice]
  gross_residency_tax = engine_dict["ordinary"](local_income)

  allowed_ftc = min(foreign_tax_paid_local, gross_residency_tax)
  net_tax_due = max(0.0, gross_residency_tax - allowed_ftc)
  effective_tax_rate = (
      (net_tax_due / local_income * 100) if local_income > 0 else 0
  )

  if is_fallback:
    st.warning(
        f"Using USD fallback FX rate (Date: {rate_date_str or 'Latest'}): 1"
        f" {source_curr} = {rate:.4f} {target_curr}"
    )
  else:
    st.success(
        f"Rate Applied (Date: {rate_date_str or 'Latest'}): 1 {source_curr} ="
        f" {rate:.4f} {target_curr}"
    )

  st.markdown("---")
  st.subheader(f"Tax Summary for Residency: {residency_choice}")

  m1, m2, m3 = st.columns(3)
  with m1:
    render_full_metric("Converted Amount", f"{target_curr} {local_income:,.2f}")
  with m2:
    render_full_metric(
        "Gross Residency Tax", f"{target_curr} {gross_residency_tax:,.2f}"
    )
  with m3:
    render_full_metric(
        "Allowed FTC Credit", f"-{target_curr} {allowed_ftc:,.2f}"
    )

  col_res1, col_res2 = st.columns(2)
  with col_res1:
    render_full_metric("Net Tax Due", f"{target_curr} {net_tax_due:,.2f}")
  with col_res2:
    render_full_metric("Effective Tax Rate", f"{effective_tax_rate:.2f}%")

  st.markdown("---")
  st.subheader("International Tax Burden Comparison")
  st.markdown(
      "Comparing tax burdens across all supported jurisdictions for the same"
      " input value."
  )

  comparison_data = []
  source_to_usd_rate, _ = fetch_exchange_rate(
      source_curr, "USD", rate_date=rate_date_str
  )
  income_in_usd = foreign_amount * source_to_usd_rate

  for country, eng in COUNTRY_ENGINES.items():
    to_local_rate, _ = fetch_exchange_rate(
        "USD", eng["curr"], rate_date=rate_date_str
    )
    country_amount = income_in_usd * to_local_rate
    country_tax = eng["ordinary"](country_amount)
    country_eff_rate = (
        (country_tax / country_amount * 100) if country_amount > 0 else 0
    )

    comparison_data.append({
        "Country": country,
        "Currency": eng["curr"],
        "Converted Amount": f"{eng['curr']} {country_amount:,.2f}",
        "Gross Tax Liability": f"{eng['curr']} {country_tax:,.2f}",
        "Effective Tax Rate (%)": round(country_eff_rate, 2),
    })

  df_comp = pd.DataFrame(comparison_data)

  st.dataframe(
      df_comp,
      column_config={
          "Country": st.column_config.TextColumn("Country", width="medium"),
          "Currency": st.column_config.TextColumn("Currency", width="small"),
          "Converted Amount": st.column_config.TextColumn(
              "Converted Amount", width="large"
          ),
          "Gross Tax Liability": st.column_config.TextColumn(
              "Gross Tax Liability", width="large"
          ),
          "Effective Tax Rate (%)": st.column_config.NumberColumn(
              "Effective Tax Rate (%)", format="%.2f%%", width="medium"
          ),
      },
      use_container_width=True,
      hide_index=True,
  )

# -----------------------------------------------------------------------------
# 4. COLORFUL SQUARE FEATURE CARDS
# -----------------------------------------------------------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Platform Features","About us","Project Information","Frequently Asked questions"])
if page=="Platform Features":
  a=1
elif page=="About us":
  a=2
elif page=="Project Information":
  a=3
else:
  a=4
if a==1:
  st.markdown("---")
  st.subheader("Platform Features & Architecture Standards")

  st.markdown(
    
    """
    <style>
    #red:hover{
    background-color: red;
    color:white;
    }
    #red{background-color: white;color: red;border: solid 1.5px red; border-radius: 10px;}
    #yellow:hover{
    background-color: rgba(181, 181, 22, 0.881);
    color:white;
    }
    #yellow{background-color: white;color: rgba(181, 181, 22, 0.881);border: solid 1.5px rgba(181, 181, 22, 0.881); border-radius: 10px;}
    #green:hover{
    background-color: green;
    color:white;
    }
    #green{background-color: white;color: green;border: solid 1.5px green; border-radius: 10px;}
    #blue:hover{
    background-color: blue;
    color:white;
    }
    #blue{background-color: white;color: blue;border: solid 1.5px blue; border-radius: 10px;}
  
    .s{margin-left: 16px;
    margin-right: 14px;
    flex-basis: 23%;
    margin-bottom:20px;
    border-radius: 10px;
    padding: 18px 12px;
    box-sizing: border-box;
    transition: 0.5s;
    cursor: pointer;
    }
    
    </style>
    
    
    
    
    <div class="row">
    <div class="s" id="red" >
        <h3 style="text-align: center;">Real-Time FX API</h3>
        <p style="size:34px" >Live and historical exchange rate integration with fallback resilience</p>  
    </div>
    <div class="s" id="yellow">
        <h3 style="text-align: center;">Zero Persistence</h3>
        <p style="size:34px">Executes calculations entirely in volatile RAM without disk logs.</p>  
    </div>
    <div class="s" id="green">
        <h3 style="text-align: center;">Tax Slab Processor</h3>
        <p style="size:34px">Computes progressive tax brackets and FTC caps with precision.</p>  
    </div>
    <div class="s" id="blue">
        <h3 style="text-align: center;">Privacy In-Memory</h3>
        <p style="size:34px">Complete user data isolation securely bound to active sessions.</p>  
    </div>

    </div>


    </html>
   
    """,
    unsafe_allow_html=True,
  )
elif(a==2):
  st.markdown("---")
  st.subheader("About us")
  st.markdown(
    """
    
        
        <div>
          <h2>Problem Statement</h2>
          <p>Cross-border earners frequently face double taxation, complex progressive tax slab disparities, and fluctuating exchange rates when filing residency taxes. Manually calculating foreign tax credits (FTC) across different international jurisdictions is error-prone and time-consuming. This project delivers an automated web application to compute precise tax liabilities, integrate live/historical FX rates via API, and enforce statutory FTC caps. Ultimately, it provides taxpayers and financial planners with accurate multi-country comparisons and transparent net tax obligations.</p>
        </div>
        <div>
         <h2>Team Members</h2>
         <ol>
            <li>Harshith Kumar D (Team Lead)</li>
            <li>Michelraj G</li>
            <li>Sriram Sundar</li>
            <li>I R Adhirathan</li>
          </ol>
        </div>
    
  
    </html>

    """,
    unsafe_allow_html=True,

    )
elif a==3:
  st.markdown("---")
  st.subheader("Project Information")
  st.markdown(
    """
     <div><pre>Here are 3 additional high-impact headings and web copy sections for your landing page, focusing on user experience, commercial viability, and product transparent disclaimers:
          ## 1. Instant Cross-Border Tax Transparency in 3 Steps
           * Subtitle / Hook: From raw earnings to net tax due in seconds—no spreadsheets or tax expertise required.
           * Content:
           * Input & Convert: Enter your gross foreign earnings, source currency, and tax withheld abroad. Our system translates everything instantly using live exchange rates.
           * Select Jurisdiction: Choose your country of residence—whether India, the US, the UK, Germany, or Japan—and let our automated engines apply local tax slabs and rebates.
           * Claim Credit: Review your net tax due and effective tax rate with automatic Foreign Tax Credit (FTC) capping applied to protect you from paying twice.</pre>
          <pre>## 2. Built for Developer Integration & API Licensing
           * Subtitle / Hook: Modular, lightweight, and engineered for fintech platforms and payroll tools.
           * Content:
           * Built as a decoupled, multi-module architecture designed for rapid integration into global HR, freelance marketplace, and fintech ecosystems.
           * Our monetisation roadmap centers on enterprise B2B API licensing, enabling third-party platforms to plug real-time tax estimation directly into their payout workflows.
           * Enjoy high availability and resilience with smart network fallbacks that keep financial calculations running even during external API downtime.</pre>
          <pre>## 3. Transparent Estimations & Compliance Integrity
           * Subtitle / Hook: Engineered for educational accuracy and computational clarity.
           * Content:
           * Our statutory tax engines model real-world bracket logic, standard deductions, and regional surcharges to provide clear computational estimates.
           * Designed to give cross-border earners an actionable baseline before consulting certified tax professionals or Chartered Accountants (CAs).
           * Clear, built-in visual guidance highlights credit caps and tax threshold notices, keeping users informed at every step of the calculation.</pre>
     </div>

    """,
    unsafe_allow_html=True,

    )
else:
  st.markdown("---")
  st.subheader("Frequently Asked questions")
  st.markdown(
    """
    <style>
    .ss{margin-left: 44px;
    margin-right: 44px;
    flex-basis: 44%;
    border-radius: 10px;
    margin-bottom: 2%;
    padding: 18px 12px;
    box-sizing: border-box;
    transition: 0.5s;
    cursor: pointer;
    }
    #br:hover{
    background-color:black ;
    color:white;
    transform: scale(1.1);
    }
    #br{background-color: white;color: black;border: solid black 1px; border-radius: 10px;}

    </style>
    <div class="row" style="margin-top: 35px;">
    <div class="ss" style="transition: transform 0.3s ease;"id="br" >
        <h3 style="text-align: center;">What is the Global Income Tax Estimator? </h3>
        <p> It is a web application that estimates ordinary income tax 
        .liabilities using country-specific tax calculation models, 
        currency conversion, and a simplified Foreign Tax Credit mechanism.</p>  

    </div>
    <div class="ss" style="transition: transform 0.3s ease;" id="br">
        <h3 style="text-align: center;">  Which countries are currently supported?</h3>
        <p> The current version supports India, the United States, 
        the United Kingdom, Germany, and Japan.</p>  
    </div>
    <div class="ss" style="transition: transform 0.3s ease;"id="br" >
        <h3 style="text-align: center;"> How do I calculate my estimated tax?</h3>
        <p>Enter your gross foreign income, source currency, and foreign 
        tax paid. Select your residency country and click 
        'Calculate and Compare Tax Liability' to view the results. </p>  
        
    </div>
    <div class="ss" style="transition: transform 0.3s ease;" id="br">
        <h3 style="text-align: center;">What is a Foreign Tax Credit (FTC)?</h3>
        <p> A Foreign Tax Credit is a mechanism that may allow eligible 
        taxpayers to claim relief for certain foreign taxes against 
        tax payable in their country of residence. Actual eligibility 
        and limits depend on the applicable tax laws.</p>  
    </div>
    <div class="ss" style="transition: transform 0.3s ease;"id="br" >
        <h3 style="text-align: center;">How are exchange rates obtained?",</h3>
        <p> The application requests the latest or historical exchange rates 
        from the Frankfurter API. If a usable API rate is unavailable, 
        the current prototype uses predefined fallback rates.</p>  
        
    </div>
    <div class="ss" style="transition: transform 0.3s ease;" id="br">
        <h3 style="text-align: center;"> Can I use historical exchange rates?</h3>
        <p>"Yes. Enable 'Use Historical Exchange Rate' and select a date. 
        The application attempts to retrieve the exchange rate for 
        that date. Tax-reporting rules may require a particular 
        conversion method or date.</p>  
    </div>
    <div class="ss" style="transition: transform 0.3s ease;"id="br" >
        <h3 style="text-align: center;">   What happens if the exchange-rate API is unavailable?</h3>
        <p> The application attempts to use predefined fallback exchange 
        rates and displays a warning. These rates are illustrative 
        and may be outdated, so the resulting estimate may be inaccurate</p>  
        
    </div>
    <div class="ss" style="transition: transform 0.3s ease;" id="br">
        <h3 style="text-align: center;">What is the difference between gross tax and net tax due?</h3>
        <p>  "Gross tax is the estimated residency-country tax before the 
        Foreign Tax Credit adjustment. Net tax due is the estimated 
        amount remaining after applying the simplified credit 
        implemented in the application."</p>  
    </div>
   
    </div>


    """,
    unsafe_allow_html=True,

    )
