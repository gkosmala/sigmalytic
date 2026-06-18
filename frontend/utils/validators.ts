
export const isValidSymbol = (symbol:string) =>
  /^[A-Z]{1,10}$/.test(symbol);
