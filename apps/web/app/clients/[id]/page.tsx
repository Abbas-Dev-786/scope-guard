"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";

type Client = {
  id: string;
  name: string;
  company: string | null;
  row_version: number;
};

type Contact = {
  id: string;
  email: string;
  display_name: string;
  role: string | null;
};

export default function ClientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [client, setClient] = useState<Client | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [contactName, setContactName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [nextClient, nextContacts] = await Promise.all([
      api<Client>(`/api/v1/clients/${id}`),
      api<Contact[]>(`/api/v1/clients/${id}/contacts`),
    ]);
    setClient(nextClient);
    setContacts(nextContacts);
    setName(nextClient.name);
    setCompany(nextClient.company ?? "");
  }, [id]);

  useEffect(() => {
    let active = true;
    Promise.all([
      api<Client>(`/api/v1/clients/${id}`),
      api<Contact[]>(`/api/v1/clients/${id}/contacts`),
    ])
      .then(([nextClient, nextContacts]) => {
        if (!active) return;
        setClient(nextClient);
        setContacts(nextContacts);
        setName(nextClient.name);
        setCompany(nextClient.company ?? "");
      })
      .catch((caught) => {
        if (active) setError(caught instanceof Error ? caught.message : "Unable to load client");
      });
    return () => { active = false; };
  }, [id]);

  async function updateClient(event: FormEvent) {
    event.preventDefault();
    if (!client) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await api<Client>(`/api/v1/clients/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ expected_row_version: client.row_version, name, company: company || null }),
      });
      await load();
      setMessage("Client updated.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update client");
    } finally { setBusy(false); }
  }

  async function addContact(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(""); setMessage("");
    try {
      await api<Contact>(`/api/v1/clients/${id}/contacts`, {
        method: "POST",
        body: JSON.stringify({ email, display_name: contactName, role: role || null }),
      });
      setEmail(""); setContactName(""); setRole("");
      await load();
      setMessage("Contact added.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to add contact");
    } finally { setBusy(false); }
  }

  return <>
    <p><Link href="/clients">← Back to clients</Link></p>
    <p className="eyebrow muted">Client workspace</p><h1>{client?.name ?? "Client"}</h1>
    <p className="lede">Updates use the loaded row version. If another session edits this record first, reload before saving again.</p>
    {error && <p className="error">{error}</p>}
    {message && <p className="success">{message}</p>}
    <form className="card row" onSubmit={updateClient}>
      <label>Name<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
      <label>Company<input value={company} onChange={(event) => setCompany(event.target.value)} /></label>
      <button disabled={busy || !client}>Save client</button>
    </form>
    <h2>Contacts</h2>
    <form className="card row" onSubmit={addContact}>
      <label>Name<input value={contactName} onChange={(event) => setContactName(event.target.value)} required /></label>
      <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
      <label>Role<input value={role} onChange={(event) => setRole(event.target.value)} /></label>
      <button disabled={busy}>Add contact</button>
    </form>
    <div className="list" style={{ marginTop: 20 }}>
      {contacts.map((contact) => <div className="listItem" key={contact.id}><div><strong>{contact.display_name}</strong><div className="muted">{contact.email}</div></div><span className="muted">{contact.role ?? "Contact"}</span></div>)}
      {!error && contacts.length === 0 && <p className="muted">No contacts yet.</p>}
    </div>
  </>;
}
