import { useEffect, useState } from "react";
import { api } from "../lib/api";

const OPCOES_RETORNO = [
  { label: "7 dias", dias: 7 },
  { label: "15 dias", dias: 15 },
  { label: "30 dias", dias: 30 },
  { label: "Outro", dias: "custom" },
];

// Modal BLOQUEANTE: aparece assim que a visita é finalizada e não pode ser
// fechado sem salvar o relatório — decisão explícita do usuário (preencher
// depois faz esquecer detalhes). Vem pré-carregado com o último status
// conhecido do cliente pra não obrigar preencher tudo de novo.
export default function RelatorioVisita({ visita, aoSalvo }) {
  const [cliente, setCliente] = useState(null);
  const [observacao, setObservacao] = useState("");
  const [retornoOpcao, setRetornoOpcao] = useState(15);
  const [retornoCustom, setRetornoCustom] = useState("");
  const [promessas, setPromessas] = useState([""]);
  const [status, setStatus] = useState("ativo");
  const [aceitaVisita, setAceitaVisita] = useState(true);
  const [motivo, setMotivo] = useState("calote");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api.get(`/api/clientes/${visita.clienteId}`).then((c) => {
      setCliente(c);
      setStatus(c.status);
      setAceitaVisita(c.aceitaVisita);
      setMotivo(c.motivoRecusaVisita || "calote");
    });
  }, [visita.clienteId]);

  function atualizarPromessa(i, valor) {
    setPromessas((lista) => lista.map((p, idx) => (idx === i ? valor : p)));
  }
  function adicionarPromessa() {
    setPromessas((lista) => [...lista, ""]);
  }
  function removerPromessa(i) {
    setPromessas((lista) => lista.filter((_, idx) => idx !== i));
  }

  async function salvar(e) {
    e.preventDefault();
    if (!observacao.trim()) {
      setErro("Descreva como foi a visita.");
      return;
    }
    setEnviando(true);
    setErro("");
    const retornoDias = retornoOpcao === "custom" ? Number(retornoCustom) || null : retornoOpcao;
    try {
      const atualizada = await api.post(`/api/visitas/${visita.id}/relatorio`, {
        observacao: observacao.trim(),
        retornoDias,
        promessas: promessas.map((p) => p.trim()).filter(Boolean),
        status,
        aceitaVisita,
        motivoRecusaVisita: aceitaVisita ? null : motivo,
      });
      aoSalvo(atualizada);
    } catch (err) {
      setErro(err.message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="modal-fundo modal-bloqueante">
      <div className="modal-ficha">
        <div className="ficha-header">
          <h2>Relatório da visita</h2>
          <p className="muted" style={{ fontSize: 13 }}>
            {cliente ? cliente.nome : "Carregando cliente…"} · visita finalizada, preencha antes de continuar
          </p>
        </div>

        <form onSubmit={salvar}>
          <div className="ficha-secao" style={{ marginTop: 12, paddingTop: 0, borderTop: "none" }}>
            <span className="filtro-titulo">Como foi a visita</span>
            <textarea
              className="input" rows={3}
              placeholder="Ex.: cliente satisfeito, fechou pedido de reposição…"
              value={observacao} onChange={(e) => setObservacao(e.target.value)}
              autoFocus
            />
          </div>

          <div className="ficha-secao">
            <span className="filtro-titulo">Retorno combinado</span>
            <div className="ficha-status">
              {OPCOES_RETORNO.map((o) => (
                <label key={o.label} className="ficha-radio">
                  <input type="radio" checked={retornoOpcao === o.dias} onChange={() => setRetornoOpcao(o.dias)} />
                  {o.label}
                </label>
              ))}
            </div>
            {retornoOpcao === "custom" && (
              <input
                className="input" type="number" min="1" placeholder="Dias"
                value={retornoCustom} onChange={(e) => setRetornoCustom(e.target.value)}
                style={{ maxWidth: 120, marginTop: 6 }}
              />
            )}
          </div>

          <div className="ficha-secao">
            <span className="filtro-titulo">Promessas feitas nesta visita</span>
            {promessas.map((p, i) => (
              <div key={i} style={{ display: "flex", gap: 6 }}>
                <input
                  className="input" placeholder="Ex.: levar amostra de parafuso"
                  value={p} onChange={(e) => atualizarPromessa(i, e.target.value)}
                />
                {promessas.length > 1 && (
                  <button type="button" className="btn btn-ghost" onClick={() => removerPromessa(i)}>Remover</button>
                )}
              </div>
            ))}
            <button type="button" className="btn btn-ghost" onClick={adicionarPromessa} style={{ alignSelf: "flex-start" }}>
              + Adicionar promessa
            </button>
          </div>

          <div className="ficha-secao">
            <span className="filtro-titulo">Status do cliente</span>
            <div className="ficha-status">
              <label className="ficha-radio">
                <input type="radio" checked={status === "ativo"} onChange={() => setStatus("ativo")} /> Ativo
              </label>
              <label className="ficha-radio">
                <input type="radio" checked={status === "inativo"} onChange={() => setStatus("inativo")} /> Inativo (fechou)
              </label>
            </div>
            <div className="ficha-status" style={{ marginTop: 8 }}>
              <label className="ficha-radio">
                <input type="radio" checked={aceitaVisita} onChange={() => setAceitaVisita(true)} /> Aceita visita
              </label>
              <label className="ficha-radio">
                <input type="radio" checked={!aceitaVisita} onChange={() => setAceitaVisita(false)} /> Não aceita visita
              </label>
            </div>
            {!aceitaVisita && (
              <select className="input" value={motivo} onChange={(e) => setMotivo(e.target.value)} style={{ marginTop: 8, maxWidth: 220 }}>
                <option value="calote">Calote — ainda compra à vista</option>
                <option value="sem-visita">Sem visita — compra por telefone</option>
              </select>
            )}
          </div>

          {erro && <div className="login-erro" style={{ marginTop: 12 }}>{erro}</div>}

          <button className="btn btn-primary" type="submit" disabled={enviando} style={{ width: "100%", justifyContent: "center", marginTop: 18 }}>
            {enviando ? "Salvando…" : "Salvar relatório e continuar"}
          </button>
        </form>
      </div>
    </div>
  );
}
