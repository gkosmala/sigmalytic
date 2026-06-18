
import React, { createContext, useContext, useState } from "react";

const ThemeContext = createContext<any>(null);

export function ThemeProvider({ children }: any) {
  const [theme, setTheme] = useState("dark");
  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useThemeContext() {
  return useContext(ThemeContext);
}
