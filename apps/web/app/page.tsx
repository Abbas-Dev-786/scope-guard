export default function Overview() {
  return (
    <>
      <p className="eyebrow muted">Workspace overview</p>
      <h1>Keep scope changes visible.</h1>
      <p className="lede">The foundation is ready for confirmed contracts, evidence-backed decisions, exact approvals, and test-mode collection. Revenue cards remain empty until those later phases create authoritative facts.</p>
      <div className="grid">
        <section className="card"><span className="muted">Proposed value</span><p className="metric">₹0</p></section>
        <section className="card"><span className="muted">Revenue protected</span><p className="metric">₹0</p></section>
        <section className="card"><span className="muted">Collected</span><p className="metric">₹0</p></section>
        <section className="card"><span className="muted">Outstanding</span><p className="metric">₹0</p></section>
      </div>
      <section className="card" style={{marginTop:24}}>
        <h2>Foundation status</h2>
        <p className="notice">Projects remain paused until a contract is extracted, corrected, and confirmed in Phase 03.</p>
      </section>
    </>
  );
}
