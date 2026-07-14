import { useState } from "react";

// Renders the Novation brand logo from public/novation-logo.svg. Drop the
// official Novation asset in at that path (same filename) to use the real logo;
// if the file is ever missing, it falls back to a text wordmark so the header
// never breaks.
export default function NovationLogo({ height = 16 }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <span className="brand-word">novation</span>;
  return (
    <img
      className="brand-logo"
      src="./novation-logo.svg"
      alt="Novation"
      style={{ height }}
      onError={() => setFailed(true)}
    />
  );
}
