import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { brl } from "../lib/format";

// Ajustes do negócio que o gerente muda sozinho, sem depender de publicação.
// Cada opção é declarada no servidor (rótulo, ajuda e limites vêm de lá), então
// esta tela não precisa saber quais existem — ela desenha o que receber.
export default function AjustesView() {
  const [opcoes, setOpcoes] = useState(null);
  const [rascunho, setRascunho] = useState({});
  const [salvando, setSalvando] = useState("");
  const [erro, setErro] = useState("");
  const [aviso, setAviso] = useState("");

  function carregar() {
    api.get("/api/configuracoes")
      .then((lista) => {
        setOpcoes(lista);
        setRascunho(Object.fromEntries(lista.map((o) => [o.chave, String(o.valor)])));
      })
      .catch((e) => setErro(e.message));
  }
  useEffect(carregar, []);

  async function salvar(opcao) {
    const valor = Number(rascunho[opcao.chave]);
    if (Number.isNaN(valor)) {
      setErro("Digite um número.");
      return;
    }
    setSalvando(opcao.chave);
    setErro("");
    setAviso("");
    try {
      const r = await api.put(`/api/configuracoes/${opcao.chave}`, { valor });
      const efeito = r.efeito;
      let texto = "Salvo.";
      if (efeito && (efeito.removidos || efeito.marcados)) {
        const partes = [];
        if (efeito.removidos) partes.push(`${efeito.removidos} deixaram de aparecer como risco`);
        if (efeito.marcados) partes.push(`${efeito.marcados} passaram a aparecer como risco`);
        texto = `Salvo — ${partes.join(" e ")}.`;
      }
      setAviso(texto);
      carregar();
    } catch (e) {
      setErro(e.message);
    } finally {
      setSalvando("");
    }
  }

  if (!opcoes) return <p className="muted">Carregando…</p>;

  return (
    <div className="ajustes">
      {erro && <div className="login-erro">{erro}</div>}
      {aviso && <div className="carteira-aviso">{aviso}</div>}

      {opcoes.map((o) => {
        const alterado = String(o.valor) !== rascunho[o.chave];
        return (
          <div key={o.chave} className="ajuste-item">
            <label className="filtro-titulo" htmlFor={o.chave}>{o.rotulo}</label>
            <p className="muted" style={{ fontSize: 13 }}>{o.ajuda}</p>
            <div className="ajuste-campo">
              <input
                id={o.chave}
                className="input"
                type="number"
                min={o.minimo}
                max={o.maximo ?? undefined}
                step="500"
                value={rascunho[o.chave] ?? ""}
                onChange={(e) => setRascunho((r) => ({ ...r, [o.chave]: e.target.value }))}
              />
              <button
                className="btn btn-primary"
                disabled={!alterado || salvando === o.chave}
                onClick={() => salvar(o)}
              >
                {salvando === o.chave ? "Salvando…" : "Salvar"}
              </button>
            </div>
            <small className="faint">
              Valor atual: {o.valor > 0 ? brl(o.valor) : "sem piso (só a posição na carteira decide)"}
            </small>
          </div>
        );
      })}
    </div>
  );
}
