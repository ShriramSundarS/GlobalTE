from datetime import date
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="Global Tax Estimator", page_icon=None, layout="wide"
)

st.title("Global Foreign Income Tax Estimator")
st.markdown(
    "Calculate foreign income tax liability, apply Foreign Tax Credits (FTC),"
    " query historical exchange rates by tax year, and compare tax burdens"
    " across countries with exact numeric display."
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
# 2. OFFICIAL TAX SLAB ENGINES
# -----------------------------------------------------------------------------


def compute_india_tax(income: float) -> float:
  taxable = max(0.0, income - 75000.0)
  tax = 0.0
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
      tax += taxable_chunk * rate
  if taxable <= 1200000.0:
    tax = max(0.0, tax - 60000.0)
  return tax * 1.04


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


COUNTRY_TAX_ENGINES = {
    "India": ("INR", compute_india_tax),
    "United States": ("USD", compute_usa_tax),
    "United Kingdom": ("GBP", compute_uk_tax),
    "Germany": ("EUR", compute_germany_tax),
    "Japan": ("JPY", compute_japan_tax),
}


def render_full_metric(label: str, value_str: str):
  st.markdown(
      f"""
      <div style="background-color: #f8f9fa; padding: 12px 16px; border-radius: 8px; border: 1px solid #e0e0e0; margin-bottom: 10px;">
          <div style="font-size: 13px; color: #6c757d; margin-bottom: 4px;">{label}</div>
          <div style="font-size: 18px; font-weight: 600; color: #1f2937; white-space: nowrap; overflow: visible;">{value_str}</div>
      </div>
      """,
      unsafe_allow_html=True,
  )


# -----------------------------------------------------------------------------
# 3. STREAMLIT UI
# -----------------------------------------------------------------------------

st.subheader("1. Tax Year & Exchange Rate Date")
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

st.subheader("2. Foreign Income & Source Tax Paid")
col1, col2, col3 = st.columns(3)

with col1:
  foreign_amount = st.number_input(
      "Gross Foreign Income", min_value=0.0, value=75000.0, step=5000.0
  )
with col2:
  source_curr = st.selectbox(
      "Source Income Currency", ["USD", "EUR", "GBP", "INR", "JPY", "CAD", "AUD"]
  )
with col3:
  foreign_tax_paid_source = st.number_input(
      f"Tax Paid at Source ({source_curr})", min_value=0.0, value=5000.0, step=500.0
  )

st.subheader("3. Residency Jurisdiction")
residency_choice = st.selectbox(
    "Residency Country (Tax Jurisdiction)", list(COUNTRY_TAX_ENGINES.keys())
)

target_curr, tax_engine = COUNTRY_TAX_ENGINES[residency_choice]

if st.button("Calculate and Compare Tax Liability", type="primary"):
  rate, is_fallback = fetch_exchange_rate(
      source_curr, target_curr, rate_date=rate_date_str
  )

  local_income = foreign_amount * rate
  foreign_tax_paid_local = foreign_tax_paid_source * rate

  gross_residency_tax = tax_engine(local_income)
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
    render_full_metric(
        "Converted Income", f"{target_curr} {local_income:,.2f}"
    )
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
      "Comparing effective tax rates across all supported jurisdictions for"
      " the same income level."
  )

  comparison_data = []
  source_to_usd_rate, _ = fetch_exchange_rate(
      source_curr, "USD", rate_date=rate_date_str
  )
  income_in_usd = foreign_amount * source_to_usd_rate

  for country, (curr, engine) in COUNTRY_TAX_ENGINES.items():
    to_local_rate, _ = fetch_exchange_rate(
        "USD", curr, rate_date=rate_date_str
    )
    country_income = income_in_usd * to_local_rate
    country_tax = engine(country_income)
    country_eff_rate = (
        (country_tax / country_income * 100) if country_income > 0 else 0
    )

    comparison_data.append({
        "Country": country,
        "Currency": curr,
        "Converted Income": f"{curr} {country_income:,.2f}",
        "Gross Tax Liability": f"{curr} {country_tax:,.2f}",
        "Effective Tax Rate (%)": round(country_eff_rate, 2),
    })

  df_comp = pd.DataFrame(comparison_data)

  st.dataframe(
      df_comp,
      column_config={
          "Country": st.column_config.TextColumn("Country", width="medium"),
          "Currency": st.column_config.TextColumn("Currency", width="small"),
          "Converted Income": st.column_config.TextColumn(
              "Converted Income", width="large"
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

  chart_df = df_comp.set_index("Country")["Effective Tax Rate (%)"]
  st.bar_chart(chart_df)
