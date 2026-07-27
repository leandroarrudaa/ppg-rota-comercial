import { useEffect, useState } from "react";
import { api, salvarSessao } from "../lib/api";

// Tela de login. Se o backend ainda não tem usuário, vira o formulário de
// criação da primeira conta (admin) — o "setup".
export default function LoginView({ aoEntrar }) {
  const [modo, setModo] = useState("carregando"); // carregando | login | setup | offline
  const [nome, setNome] = useState("");
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    api.get("/api/auth/status")
      .then((s) => setModo(s.precisa_setup ? "setup" : "login"))
      .catch(() => setModo("offline"));
  }, []);

  async function enviar(e) {
    e.preventDefault();
    setErro("");
    setEnviando(true);
    try {
      const r = modo === "setup"
        ? await api.post("/api/auth/setup", { nome, usuario, senha })
        : await api.post("/api/auth/login", { usuario, senha });
      salvarSessao(r.token, r.usuario);
      aoEntrar(r.usuario);
    } catch (err) {
      setErro(err.message);
    } finally {
      setEnviando(false);
    }
  }

  if (modo === "carregando") {
    return <div className="login-fundo"><div className="login-card"><p className="muted">Conectando…</p></div></div>;
  }
  if (modo === "offline") {
    return (
      <div className="login-fundo">
        <div className="login-card">
          <h2>Servidor indisponível</h2>
          <p className="muted">Não foi possível conectar ao servidor. Verifique a internet e recarregue a página.</p>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>Tentar de novo</button>
        </div>
      </div>
    );
  }

  return (
    <div className="login-fundo">
      <form className="login-card" onSubmit={enviar}>
        <img src="/ppg-logo.webp" alt="PPG" className="login-logo" />
        <h2>{modo === "setup" ? "Criar conta do administrador" : "Entrar"}</h2>
        {modo === "setup" && (
          <p className="muted" style={{ fontSize: 13 }}>
            Primeiro acesso: crie a conta principal (administrador).
          </p>
        )}
        {modo === "setup" && (
          <label className="login-campo">
            <span>Nome</span>
            <input value={nome} onChange={(e) => setNome(e.target.value)} required autoFocus />
          </label>
        )}
        <label className="login-campo">
          <span>Usuário</span>
          <input value={usuario} onChange={(e) => setUsuario(e.target.value)} required autoFocus={modo === "login"} autoCapitalize="none" />
        </label>
        <label className="login-campo">
          <span>Senha</span>
          <input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} required minLength={4} />
        </label>
        {erro && <div className="login-erro">{erro}</div>}
        <button className="btn btn-primary" type="submit" disabled={enviando} style={{ width: "100%", justifyContent: "center" }}>
          {enviando ? "Enviando…" : modo === "setup" ? "Criar conta e entrar" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
