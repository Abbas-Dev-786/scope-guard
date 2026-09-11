"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type Me={id:string;verified_email:string;timezone:string;status:string;row_version:number};
type Preference={id:string;version:number;rate_minor:number;minimum_minor:number;increment_minor:number;communication_style:string};

export default function SettingsPage(){
  const [me,setMe]=useState<Me|null>(null);const [preference,setPreference]=useState<Preference|null>(null);const [error,setError]=useState("");const [message,setMessage]=useState("");
  const load=useCallback(async()=>{try{const [owner,prefs]=await Promise.all([api<Me>("/api/v1/me"),api<Preference>("/api/v1/preferences")]);setMe(owner);setPreference(prefs);setError("");}catch(caught){setError(caught instanceof Error?caught.message:"Unable to load preferences");}},[]);
  useEffect(() => {
    let active = true;
    Promise.all([api<Me>("/api/v1/me"), api<Preference>("/api/v1/preferences")])
      .then(([owner, prefs]) => {
        if (active) { setMe(owner); setPreference(prefs); setError(""); }
      })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Unable to load preferences"); });
    return () => { active = false; };
  }, []);
  async function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();if(!me||!preference)return;const form=new FormData(event.currentTarget);try{await api<Preference>("/api/v1/preferences",{method:"PATCH",body:JSON.stringify({expected_row_version:me.row_version,rate_minor:Number(form.get("rate_minor")),minimum_minor:Number(form.get("minimum_minor")),increment_minor:Number(form.get("increment_minor")),communication_style:String(form.get("communication_style")),reminder_policy:{approval_required:true,steps_days:[3,7,14]}})});setMessage("A new immutable preference version was created.");await load();}catch(caught){setError(caught instanceof Error?caught.message:"Unable to save preferences");}}
  return <><p className="eyebrow muted">Commercial policy</p><h1>Preferences</h1><p className="lede">All values are integer paise. They are frozen into versioned project and proposal inputs; model memory cannot replace them.</p>{error&&<p className="error">{error} <Link href="/sign-in">Open sign in</Link></p>}{message&&<p className="success">{message}</p>}{me&&preference&&<form className="card stack" onSubmit={submit}><p><strong>{me.verified_email}</strong><br/><span className="muted">{me.timezone} · account v{me.row_version} · preference v{preference.version}</span></p><div className="row"><label>Rate (paise/hour)<input name="rate_minor" type="number" min="1" max="100000000" defaultValue={preference.rate_minor}/></label><label>Minimum (paise)<input name="minimum_minor" type="number" min="1" max="100000000" defaultValue={preference.minimum_minor}/></label><label>Round to (paise)<input name="increment_minor" type="number" min="1" max="100000000" defaultValue={preference.increment_minor}/></label><label>Communication style<input name="communication_style" defaultValue={preference.communication_style}/></label></div><button>Save as new version</button></form>}</>;
}
