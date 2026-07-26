import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import DashboardIcon from "@mui/icons-material/Dashboard";
import TimelineIcon from "@mui/icons-material/Timeline";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import ReportProblemIcon from "@mui/icons-material/ReportProblem";
import TrackChangesIcon from "@mui/icons-material/TrackChanges";
import GavelIcon from "@mui/icons-material/Gavel";
import AddBoxIcon from "@mui/icons-material/AddBox";
import LogoutIcon from "@mui/icons-material/Logout";
import RefreshIcon from "@mui/icons-material/Refresh";
import LightModeIcon from "@mui/icons-material/LightMode";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import MenuIcon from "@mui/icons-material/Menu";
import { tokens } from "../theme";

const navItems = [
  ["dashboard", "Dashboard", DashboardIcon],
  ["traces", "Traces", TimelineIcon],
  ["explorer", "Trace explorer", AccountTreeIcon],
  ["incidents", "Incidents", ReportProblemIcon],
  ["slos", "SLOs", TrackChangesIcon],
  ["governance", "Governance", GavelIcon],
  ["create", "Create project", AddBoxIcon]
];

const drawerWidth = 226;

function BrandMark({ small = false }) {
  return (
    <Box
      component="img"
      src="/favicon.svg"
      alt="AgentSRE logo"
      sx={{
        width: small ? 32 : 48,
        height: small ? 32 : 48,
        borderRadius: small ? 1 : 1.25,
        display: "block",
        flex: "0 0 auto",
        boxShadow: "0 0 34px rgba(65, 166, 255, 0.28)"
      }}
    />
  );
}

function NavContent({ page, setPage, logout, close, user = "sre.lead@redacted.example", projects = [], selectedProjectId = "", onProjectChange }) {
  const projectValue = projects.some((project) => project.project_id === selectedProjectId) ? selectedProjectId : "";
  return (
    <Stack sx={{ height: "100%", p: 1.6 }} spacing={1.6}>
      <Stack direction="row" spacing={1} alignItems="center">
        <BrandMark small />
        <Typography sx={{ fontWeight: 760, fontSize: 16 }}>AgentSRE</Typography>
      </Stack>

      <FormControl size="small" sx={{ display: { sm: "none" } }}>
        <Select
          value={projectValue}
          displayEmpty
          onChange={(event) => onProjectChange?.(event.target.value)}
        >
          <MenuItem value="" disabled>{projects.length ? "Select project" : "No project yet"}</MenuItem>
          {projects.map((project) => (
            <MenuItem key={project.project_id} value={project.project_id}>
              {project.project_name}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <Stack spacing={0.45} component="nav" sx={{ flex: 1 }}>
        {navItems.map(([id, label, Icon]) => (
          <Button
            key={id}
            startIcon={<Icon fontSize="small" />}
            onClick={() => {
              setPage(id);
              close?.();
            }}
            sx={{
              justifyContent: "flex-start",
              minHeight: 36,
              px: 1.15,
              fontSize: 12.5,
              color: page === id ? "text.primary" : "text.secondary",
              border: "1px solid",
              borderColor: page === id ? "rgba(65, 166, 255, 0.28)" : "transparent",
              background: page === id ? "linear-gradient(90deg, rgba(65,166,255,.16), transparent)" : "transparent",
              "& .MuiButton-startIcon": { mr: 0.9 }
            }}
          >
            {label}
          </Button>
        ))}
      </Stack>

      <Divider />
      <Stack spacing={0.8}>
        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 650, overflowWrap: "anywhere" }}>
          {user}
        </Typography>
        <Button startIcon={<LogoutIcon fontSize="small" />} variant="outlined" size="small" onClick={logout}>
          Logout
        </Button>
      </Stack>
    </Stack>
  );
}

function TopBar({ mode, setMode, refresh, openNav, projects = [], selectedProjectId = "", onProjectChange }) {
  const isDark = mode === "dark";
  const projectValue = projects.some((project) => project.project_id === selectedProjectId) ? selectedProjectId : "";
  const longestProjectName = Math.max(
    "Select project".length,
    ...projects.map((project) => String(project.project_name || "").length),
  );
  const projectSelectWidth = `${Math.max(18, longestProjectName + 5)}ch`;
  const controlSx = {
    bgcolor: isDark ? "rgba(17, 24, 33, 0.9)" : "rgba(255, 255, 255, 0.82)",
    border: "1px solid",
    borderColor: "divider"
  };

  return (
    <Box
      component="header"
      sx={{
        position: "sticky",
        top: 0,
        zIndex: 10,
        minHeight: { xs: 68, md: 74 },
        px: { xs: 1.25, md: 2.1 },
        py: { xs: 1, md: 1.35 },
        display: "flex",
        alignItems: "center",
        gap: { xs: 0.85, md: 1.2 },
        bgcolor: isDark ? "rgba(5, 9, 15, 0.88)" : "rgba(238, 243, 248, 0.88)",
        backdropFilter: "blur(16px)",
        borderBottom: "1px solid",
        borderColor: "divider"
      }}
    >
      <IconButton onClick={openNav} aria-label="Open navigation" sx={{ ...controlSx, display: { md: "none" }, flexShrink: 0 }}>
        <MenuIcon fontSize="small" />
      </IconButton>
      <Typography variant="h4" sx={{ fontWeight: 760, fontSize: { xs: 18, sm: 22, md: 26 }, whiteSpace: "nowrap" }}>
        Agent Operations
      </Typography>

      <Box
        sx={{
          ml: "auto",
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          gap: { xs: 0.5, md: 0.65 },
          flexShrink: 0,
          minWidth: 0
        }}
      >
        <FormControl
          size="small"
          sx={{
            display: { xs: "none", sm: "block" },
            width: projectSelectWidth,
            maxWidth: { sm: "42vw", lg: 460 },
            flexShrink: 0,
          }}
        >
          <Select
            value={projectValue}
            displayEmpty
            onChange={(event) => onProjectChange?.(event.target.value)}
            renderValue={(value) => {
              if (!value) {
                return projects.length ? "Select project" : "No project yet";
              }
              return projects.find((project) => project.project_id === value)?.project_name || value;
            }}
            sx={{
              bgcolor: isDark ? "rgba(11, 15, 23, .78)" : "rgba(255, 255, 255, .84)",
              "& .MuiSelect-select": {
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                pr: 4
              }
            }}
          >
            <MenuItem value="" disabled>
              {projects.length ? "Select project" : "No project yet"}
            </MenuItem>
            {projects.map((project) => (
              <MenuItem key={project.project_id} value={project.project_id}>
                {project.project_name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <IconButton onClick={refresh} aria-label="Refresh" sx={controlSx}>
          <RefreshIcon fontSize="small" />
        </IconButton>
        <IconButton onClick={() => setMode(isDark ? "light" : "dark")} aria-label="Toggle theme" sx={controlSx}>
          {isDark ? <LightModeIcon fontSize="small" /> : <DarkModeIcon fontSize="small" />}
        </IconButton>
      </Box>
    </Box>
  );
}

export default function AppShell({ children, page, setPage, mode, setMode, logout, refresh, projects, selectedProjectId, onProjectChange, user }) {
  const isDark = mode === "dark";
  const [mobileOpen, setMobileOpen] = useState(false);
  const closeMobileNav = () => setMobileOpen(false);

  return (
    <Box sx={{ minHeight: "100vh", display: "flex" }}>
      <Box
        component="aside"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          display: { xs: "none", md: "block" },
          borderRight: "1px solid",
          borderColor: "divider",
          bgcolor: isDark ? tokens.bgSoft.dark : tokens.bgSoft.light,
          position: "sticky",
          top: 0,
          height: "100vh"
        }}
      >
        <NavContent
          page={page}
          setPage={setPage}
          logout={logout}
          user={user?.email || user?.display_name}
          projects={projects}
          selectedProjectId={selectedProjectId}
          onProjectChange={onProjectChange}
        />
      </Box>

      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Drawer
          open={mobileOpen}
          onClose={closeMobileNav}
          ModalProps={{ keepMounted: true }}
          PaperProps={{
            sx: {
              width: 270,
              bgcolor: isDark ? tokens.bgSoft.dark : tokens.bgSoft.light,
              backgroundImage: "none"
            }
          }}
        >
          <NavContent
            page={page}
            setPage={setPage}
            logout={logout}
            close={closeMobileNav}
            user={user?.email || user?.display_name}
            projects={projects}
            selectedProjectId={selectedProjectId}
            onProjectChange={onProjectChange}
          />
        </Drawer>
        <TopBar
          mode={mode}
          setMode={setMode}
          refresh={refresh}
          openNav={() => setMobileOpen(true)}
          projects={projects}
          selectedProjectId={selectedProjectId}
          onProjectChange={onProjectChange}
        />
        <Box component="main" sx={{ maxWidth: 1440, mx: "auto", px: { xs: 1.25, md: 2.1 }, py: { xs: 1.5, md: 2.15 } }}>
          {children}
        </Box>
      </Box>
    </Box>
  );
}

export { BrandMark };
