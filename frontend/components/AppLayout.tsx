
import React from "react";
import Navbar from "./Navbar";
import Sidebar from "./Sidebar";

export default function AppLayout({children}: any) {
  return (
    <div>
      <Navbar />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-4">{children}</main>
      </div>
    </div>
  );
}
