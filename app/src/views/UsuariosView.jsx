import { useEffect, useState } from "react";
import { api } from "../lib/api";

// Painel do admin: cria e remove contas (ex.: o login do Taborda pra campo).
export default function UsuariosView({ usuarioAtual }) {
  const [usuarios, setUsuarios] = useState(null);
  const [nome, setNome] = useState("");
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [papel, setPapel] = useState("vendedor");
  const [criando, setCriando] = useState(false);
  const [erro, setErro] = useState("");

  function carregar() {
    api.get("/api/auth/usuarios").then(setUsuarios).catch((e) => setErro(e.message));
  }

  useEffect(() => { carregar(); }, []);

  async function criar(e) {
    e.preventDefault();
    setCriando(true);
    setErro("");
    try {
      await api.post("/api/auth/usuarios", { nome, usuario, senha, papel });
      setNome(""); setUsuario(""); setSenha(""); setPapel("vendedor");
      carregar();
    } catch (err) {
      setErro(err.message);
    } finally {
      setCriando(false);
    }
  }

  async function remover(id) {
    try {
      await api.del(`/api/auth/usuarios/${id}`);
      setUsuarios((lista) => lista.filter((u) => u.id !== id));
    } catch (err) {
      setErro(err.message);
    }
  }

  return (
    <div className="vazio" style={{ display: "block", padding: "32px 40px", overflowY: "auto" }}>
      <div style={{ maxWidth: 560, margin: "0 auto" }}>
        <h3 style={{ marginBottom: 6 }}>Usuários</h3>
        <p className="muted" style={{ fontSize: 13, marginBottom: 20 }}>
          Crie o acesso do Taborda (perfil Vendedor) ou de outro admin.
        </p>

        <form onSubmit={criar} className="cliente-card" style={{ background: "var(--surface)", color: "var(--ink)", display: "flex", flexDirection: "column", gap: 10 }}>
          <input className="input" placeholder="Nome" value={nome} onChange={(e) => setNome(e.target.value)} required />
          <input className="input" placeholder="Usuário (login)" value={usuario} onChange={(e) => setUsuario(e.target.value)} required autoCapitalize="none" />
          <input className="input" type="password" placeholder="Senha" value={senha} onChange={(e) => setSenha(e.target.value)} required minLength={4} />
          <select className="input" value={papel} onChange={(e) => setPapel(e.target.value)}>
            <option value="vendedor">Vendedor (campo)</option>
            <option value="admin">Admin (gestão completa)</option>
          </select>
          <button className="btn btn-primary" type="submit" disabled={criando} style={{ justifyContent: "center" }}>
            {criando ? "Criando…" : "Criar usuário"}
          </button>
          {erro && <div className="login-erro">{erro}</div>}
        </form>

        <div style={{ marginTop: 24 }}>
          <span className="filtro-titulo">Contas existentes</span>
          {!usuarios ? (
            <p className="muted" style={{ marginTop: 8 }}>Carregando…</p>
          ) : (
            <ul className="vinculo-membros" style={{ marginTop: 8 }}>
              {usuarios.map((u) => (
                <li key={u.id}>
                  <span>{u.nome} · {u.usuario} · <span className="chip chip-motivo">{u.papel}</span></span>
                  {u.id !== usuarioAtual?.id && (
                    <button className="btn btn-ghost" onClick={() => remover(u.id)}>Remover</button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
