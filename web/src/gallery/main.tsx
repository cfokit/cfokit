import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../index.css";
import { Gallery } from "./Gallery";

const root = document.getElementById("root");
if (root === null) throw new Error("gallery.html has no #root element");

createRoot(root).render(
  <StrictMode>
    <Gallery />
  </StrictMode>,
);
