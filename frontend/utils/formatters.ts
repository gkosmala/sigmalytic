
export const formatPercent = (v:number) =>
  `${v.toFixed(2)}%`;

export const formatCurrency = (v:number) =>
  `$${v.toLocaleString()}`;
