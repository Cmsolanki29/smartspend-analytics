/** Safe INR display — never NaN or undefined for new users. */
export function formatCurrency(amount) {
  const num = Number(amount);
  if (!Number.isFinite(num)) return "₹0";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(num);
}

export default formatCurrency;
