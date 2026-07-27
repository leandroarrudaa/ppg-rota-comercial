import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { brl } from "../lib/format";

// Painel do admin: gera e revisa sugestões automáticas de vínculo de CNPJ
// (nome parecido / mesmo CEP-endereço). Aceitar cria o "cliente mestre";
// recusar não faz a sugestão reaparecer.
export default function SugestoesVinculoView() {
  const [sugestoes, setSugestoes] = useState(null);
  const [gerando, setGerando] = useState(false);
  const [resolvendo, setResolvendo] = useState(null);
  const [erro, setErro] = useState("");

  function carregar() {
    api.get("/api/vinculos/sugestoes").then(setSugestoes).catch((e) => setErro(e.message));
  }

  useEffect(() => { carregar(); }, []);

  async function gerar() {
    setGerando(true);
    setErro("");
    try {
      await api.post("/api/vinculos/gerar-sugestoes", {});
      carregar();
    } catch (e) {
      setErro(e.message);
    } finally {
      setGerando(false);
    }
  }

  async function resolver(id, aceitar) {
    setResolvendo(id);
    try {
      await api.patch(`/api/vinculos/sugestoes/${id}`, { aceitar });
      setSugestoes((lista) => lista.filter((s) => s.id !== id));
    } catch (e) {
      setErro(e.message);
    } finally {
      setResolvendo(null);
    }
  }

  return (
    <div className="vazio" style={{ display: "block", padding: "32px 40px", overflowY: "auto" }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <h3 style={{ marginBottom: 6 }}>Sugestões de vínculo de CNPJ</h3>
        <p className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
          Candidatos a mesma empresa (nome parecido e/ou endereço exato — rua e número). Aceitar agrupa o RFM dos dois CNPJs.
        </p>
        <button className="btn btn-primary" onClick={gerar} disabled={gerando} style={{ marginBottom: 20 }}>
          {gerando ? "Gerando…" : "Gerar novas sugestões"}
        </button>
        {erro && <div className="login-erro" style={{ marginBottom: 16 }}>{erro}</div>}

        {!sugestoes ? (
          <p className="muted">Carregando…</p>
        ) : sugestoes.length === 0 ? (
          <p className="muted">Nenhuma sugestão pendente no momento.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {sugestoes.map((s) => (
              <div key={s.id} className="cliente-card" style={{ background: "var(--surface)", color: "var(--ink)" }}>
                <div className="stat-top">
                  <span className="chip chip-motivo">{s.motivo}</span>
                  <span className="faint" style={{ fontSize: 12 }}>confiança {(s.score * 100).toFixed(0)}%</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 16, marginTop: 10 }}>
                  <div>
                    <b>{s.clienteA.nome}</b>
                    <p className="muted" style={{ fontSize: 12 }}>CNPJ {s.clienteA.cnpj || "—"}</p>
                    <p className="muted" style={{ fontSize: 12 }}>{s.clienteA.endereco || "sem endereço"}{s.clienteA.cidade ? `, ${s.clienteA.cidade}` : ""}</p>
                    <p className="muted" style={{ fontSize: 12 }}>{s.clienteA.faixa || "sem faixa"} · {brl(s.clienteA.fat)}</p>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <b>{s.clienteB.nome}</b>
                    <p className="muted" style={{ fontSize: 12 }}>CNPJ {s.clienteB.cnpj || "—"}</p>
                    <p className="muted" style={{ fontSize: 12 }}>{s.clienteB.endereco || "sem endereço"}{s.clienteB.cidade ? `, ${s.clienteB.cidade}` : ""}</p>
                    <p className="muted" style={{ fontSize: 12 }}>{s.clienteB.faixa || "sem faixa"} · {brl(s.clienteB.fat)}</p>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                  <button className="btn btn-primary" disabled={resolvendo === s.id} onClick={() => resolver(s.id, true)}>
                    É a mesma empresa
                  </button>
                  <button className="btn btn-ghost" disabled={resolvendo === s.id} onClick={() => resolver(s.id, false)}>
                    Não é
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
