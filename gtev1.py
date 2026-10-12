from decimal import Decimal
import requests
import streamlit as st

st.set_page_config(
    page_title="Global Tax & Foreign Income Estimator",
    page_icon="🧮",
    layout="centered",
)

st.title("🧮 Global Tax & Foreign Income Estimator")
st.markdown(
    "Calculate foreign income tax liability in your residency currency using live exchange rates."
)

# Sidebar inputs for configuration
st.sidebar.header("Configuration")
residency_country = st.sidebar.selectbox(
    "Residency Country (Tax Jurisdiction)",
    ["United States", "United Kingdom", "Canada", "Australia", "Germany"],
)
target_currency = st.sidebar.selectbox(
    "Residency Currency", ["USD", "GBP", "CAD", "AUD", "EUR"]
)

# Main input form
st.markdown("### Income & Currency Details")
col1, col2 = st.columns(2)

with col1:
    foreign_amount = st.number_input(
        "Foreign Income Amount", min_value=0.0, value=75000.0, step=1000.0
    )
with col2:
    source_currency = st.selectbox(
        "Income Source Currency", ["USD", "EUR", "GBP", "AUD", "CAD", "INR", "JPY"]
    )


# Function to fetch live exchange rates with caching
@st.cache_data(ttl=3600)  # Cache for 1 hour to avoid rate limits
def fetch_exchange_rate(base, target):
  try:
    url = f"https://api.exchangerate-api.com/v4/latest/{base}"
    response = requests.get(url, timeout=5)
    if response.status_code == 200:
      data = response.json()
      return data["rates"].get(target)
  except Exception:
    return None
  return None


# Simple mock progressive tax brackets based on target currency
def calculate_tax(income_decimal, country):
  # Simplified progressive brackets for demonstration
  if country == "United States":
    # Simple mock bracket: 10% up to 11,000, 12% up to 44,725, 22% above
    if income_decimal <= 11000:
      return income_decimal * Decimal("0.10")
    elif income_decimal <= 44725:
      return Decimal("1100") + (income_decimal - Decimal("11000")) * Decimal(
          "0.12"
      )
    else:
      return Decimal("5147") + (income_decimal - Decimal("44725")) * Decimal(
          "0.22"
      )
  else:
    # Generic progressive mock
    if income_decimal <= 50000:
      return income_decimal * Decimal("0.15")
    else:
      return Decimal("7500") + (income_decimal - Decimal("50000")) * Decimal(
          "0.25"
      )


if st.button("Calculate Tax Liability", type="primary"):
  if source_currency == target_currency:
    rate = Decimal("1.0")
    converted_income = Decimal(str(foreign_amount))
    st.info("Source and target currencies are identical. No conversion needed.")
  else:
    with st.spinner("Fetching live exchange rates..."):
      raw_rate = fetch_exchange_rate(source_currency, target_currency)

    if raw_rate:
      rate = Decimal(str(raw_rate))
      converted_income = Decimal(str(foreign_amount)) * rate
      st.success(
          f"Live Rate: 1 {source_currency} = {rate:.4f} {target_currency}"
      )
    else:
      st.error(
          "Failed to fetch live exchange rates from API. Please try again later."
      )
      st.stop()

  # Calculate tax using precision Decimal types
  estimated_tax = calculate_tax(converted_income, residency_country)
  effective_rate = (
      (estimated_tax / converted_income) * 100 if converted_income > 0 else 0
  )

  # Display results in clean metrics
  st.markdown("---")
  st.subheader("Estimation Summary")

  m1, m2, m3 = st.columns(3)
  m1.metric(
      "Converted Income",
      f"{target_currency} {float(converted_income):,.2f}",
      f"From {source_currency} {foreign_amount:,.2f}",
  )
  m2.metric(
      "Estimated Tax Liability", f"{target_currency} {float(estimated_tax):,.2f}"
  )
  m3.metric("Effective Tax Rate", f"{float(effective_rate):.2f}%")
