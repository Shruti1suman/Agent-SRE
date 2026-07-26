import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

export default function DataTable({
  columns,
  rows,
  getKey,
  onRowClick,
  emptyMessage = "No records found.",
  pageSize = 10,
  scrollX = false,
  minWidth = "100%"
}) {
  const safeRows = rows || [];
  const [page, setPage] = useState(0);
  const totalPages = Math.max(1, Math.ceil(safeRows.length / pageSize));
  const shouldPaginate = safeRows.length > pageSize;
  const visibleRows = useMemo(
    () => safeRows.slice(page * pageSize, page * pageSize + pageSize),
    [safeRows, page, pageSize],
  );

  useEffect(() => {
    setPage(0);
  }, [safeRows.length, pageSize]);

  useEffect(() => {
    if (page > totalPages - 1) {
      setPage(Math.max(0, totalPages - 1));
    }
  }, [page, totalPages]);

  return (
    <TableContainer
      component={Paper}
      variant="outlined"
      sx={{
        width: "100%",
        overflowX: scrollX ? "auto" : "hidden",
        bgcolor: (theme) => theme.palette.mode === "dark" ? "rgba(17, 24, 33, 0.86)" : "rgba(255, 255, 255, 0.9)",
        borderColor: "rgba(151, 172, 203, 0.15)",
        borderRadius: 1
      }}
    >
      <Table size="small" sx={{ width: "100%", minWidth, tableLayout: "fixed" }}>
        <TableHead>
          <TableRow>
            {columns.map((column) => (
              <TableCell key={column.id} sx={{ width: column.width, color: "text.secondary", fontSize: 10, fontWeight: 700, textTransform: "uppercase", py: 1.15 }}>
                {column.label}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {safeRows.length ? visibleRows.map((row, index) => (
            <TableRow key={getKey ? getKey(row) : page * pageSize + index} hover={Boolean(onRowClick)} onClick={() => onRowClick?.(row)} sx={{ cursor: onRowClick ? "pointer" : "default" }}>
              {columns.map((column) => (
              <TableCell
                key={column.id}
                sx={{
                  width: column.width,
                  py: 1.05,
                  fontSize: 14,
                  verticalAlign: "middle",
                  overflow: "hidden",
                  overflowWrap: "anywhere",
                  wordBreak: "break-word"
                }}
              >
                {column.render ? column.render(row) : row[column.id]}
              </TableCell>
              ))}
            </TableRow>
          )) : (
            <TableRow>
              <TableCell colSpan={columns.length} sx={{ py: 3 }}>
                <Typography color="text.secondary" sx={{ textAlign: "center" }}>{emptyMessage}</Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {shouldPaginate ? (
        <Box
          sx={{
            px: 1.4,
            py: 1,
            borderTop: "1px solid",
            borderColor: "divider",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 1
          }}
        >
          <Typography color="text.secondary" sx={{ fontSize: 12.5 }}>
            Showing {page * pageSize + 1}-{Math.min((page + 1) * pageSize, safeRows.length)} of {safeRows.length}
          </Typography>
          <Box sx={{ display: "flex", gap: 0.75 }}>
            <Button size="small" variant="outlined" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}>
              Previous
            </Button>
            <Button size="small" variant="outlined" disabled={page >= totalPages - 1} onClick={() => setPage((value) => Math.min(totalPages - 1, value + 1))}>
              Next
            </Button>
          </Box>
        </Box>
      ) : null}
    </TableContainer>
  );
}
