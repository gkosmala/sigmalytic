
import Link from "next/link";

export default function Sidebar() {
  return (
    <aside className="w-64 border-r p-4">
      <div className="space-y-2">
        <Link href="/">Dashboard</Link><br/>
        <Link href="/status-center">Status Center</Link><br/>
        <Link href="/operator-dominance">Operator Dominance</Link>
      </div>
    </aside>
  );
}
