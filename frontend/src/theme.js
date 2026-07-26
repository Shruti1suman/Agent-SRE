import { createTheme } from "@mui/material/styles";

const base = {
  shape: { borderRadius: 8 },
  typography: {
    fontFamily: 'Inter, "Segoe UI", Arial, sans-serif',
    fontSize: 13,
    button: { textTransform: "none", fontWeight: 650 },
    h1: { fontWeight: 760, letterSpacing: 0, fontSize: "2rem" },
    h2: { fontWeight: 740, letterSpacing: 0, fontSize: "1.6rem" },
    h3: { fontWeight: 700, letterSpacing: 0, fontSize: "1.35rem" },
    h4: { fontWeight: 760, letterSpacing: 0, fontSize: "1.55rem" },
    h5: { fontWeight: 760, letterSpacing: 0, fontSize: "1.25rem" },
    h6: { fontWeight: 760, letterSpacing: 0, fontSize: "1rem" },
    body1: { fontSize: "0.88rem" },
    body2: { fontSize: "0.8rem" },
    caption: { fontSize: "0.68rem" }
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 8, minHeight: 34 }
      }
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: "none" }
      }
    },
    MuiCard: {
      styleOverrides: {
        root: { borderRadius: 8 }
      }
    },
    MuiIconButton: {
      styleOverrides: {
        root: { borderRadius: 8 }
      }
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderBottomColor: "rgba(151, 172, 203, 0.12)" }
      }
    }
  }
};

export function makeTheme(mode) {
  const dark = mode === "dark";
  return createTheme({
    ...base,
    palette: {
      mode,
      primary: { main: "#41a6ff" },
      secondary: { main: "#69e6d3" },
      success: { main: "#37d39a" },
      warning: { main: "#f6bc45" },
      error: { main: "#ff6270" },
      background: {
        default: dark ? "#05090f" : "#eef3f8",
        paper: dark ? "#111821" : "#ffffff"
      },
      text: {
        primary: dark ? "#eef4ff" : "#132034",
        secondary: dark ? "#8ea0b8" : "#5e6c7f"
      },
      divider: dark ? "rgba(151, 172, 203, 0.18)" : "rgba(46, 66, 92, 0.16)"
    }
  });
}

export const tokens = {
  bgSoft: { dark: "#0b1118", light: "#f7faff" },
  panel2: { dark: "#151f2b", light: "#f2f6fb" },
  shadow: {
    dark: "0 20px 70px rgba(0, 0, 0, 0.35)",
    light: "0 20px 55px rgba(57, 77, 110, 0.14)"
  }
};
