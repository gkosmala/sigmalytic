
import Link from "next/link";

export default function Navbar() {
  return (
    <nav className="p-4 border-b flex gap-4">
      <Link href="/">Dashboard</Link>
      <Link href="/campaigns">Campaigns</Link>
      <Link href="/opportunities">Opportunities</Link>
      <Link href="/research">Research</Link>
      <Link href="/rankings">Rankings</Link>
    </nav>
  );
}
