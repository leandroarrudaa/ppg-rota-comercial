import { useMemo, useState } from "react";
import { scriptContato } from "../lib/recomendacao";
import { gerarPdfContato } from "../lib/pdf";
import { DIAS } from "../lib/rota";
import { FAIXA_COR, FAIXA_CHIP, FAIXA_DOT, brl, telefoneFmt, recenciaTexto } from "../lib/format";

const PRIO_PESO = { Alta: 0, Média: 1, Baixa: 2 };
const FXKEY = { Ouro: "gold", Prata: "silver", Bronze: "bronze" };
const prioClasse = (p) => "prio prio-" + p.toLowerCase().normalize("NFD").replace(/[^a-z]/g, "");

export default function ContatoView({ clientes }) {
  const [porDia, setPorDia] = useState(20);
  const [dia, setDia] = useState(0);
  const [aberto, setAberto] = useState(null);

  // fila priorizada: prioridade do contato, depois maior faturamento histórico
  const fila = useMemo(() => {
    return [...clientes]
      .map((c) => ({ c, s: scriptContato(c) }))
      .sort((a, b) => {
        const p = PRIO_PESO[a.s.prioridade] - PRIO_PESO[b.s.prioridade];
        return p !== 0 ? p : (b.c.fat || 0) - (a.c.fat || 0);
      });
  }, [clientes]);

  const doDia = useMemo(() => fila.slice(dia * porDia, dia * porDia + porDia), [fila, dia, porDia]);
  const valorDia = doDia.reduce((s, x) => s + (x.c.fat || 0), 0);
  const comTelefone = doDia.filter((x) => x.c.telefone).length;

  if (!clientes.length) return <div className="vazio">Nenhum cliente adormecido neste período.</div>;

  return (
    <div className="mapa-layout contato-layout">
      <aside className="painel painel-largo">
        <div className="painel-head">
          <h3>Plano de contato</h3>
          <p className="muted" style={{ fontSize: 13 }}>Reativar adormecidos · agendar visita</p>
        </div>

        <div className="dias">
          {DIAS.map((d, i) => (
            <button key={d} className={"dia-btn" + (i === dia ? " on" : "")} onClick={() => setDia(i)}>
              {d.slice(0, 3)}
            </button>
          ))}
        </div>

        <div className="filtro-grupo">
          <span className="filtro-titulo">Contatos por dia: <b>{porDia}</b></span>
          <input type="range" min="10" max="50" value={porDia} onChange={(e) => { setPorDia(+e.target.value); setDia(0); }} className="slider" />
        </div>

        <div className="resumo">
          <div className="resumo-item"><span>Contatos do dia</span><b>{doDia.length}</b></div>
          <div className="resumo-item"><span>Com telefone</span><b>{comTelefone}/{doDia.length}</b></div>
          <div className="resumo-item"><span>Total adormecidos</span><b>{clientes.length}</b></div>
          <div className="resumo-item destaque"><span>Potencial de reativação</span><b>{brl(valorDia)}</b></div>
        </div>

        <button
          className="btn btn-primary"
          style={{ width: "100%", justifyContent: "center" }}
          onClick={() => gerarPdfContato({ diaNome: DIAS[dia], clientes: doDia.map((x) => x.c) })}
        >
          Baixar lista de contatos
        </button>
      </aside>

      {/* lista grande de contatos */}
      <div className="contato-lista-wrap">
        <ol className="contato-lista">
          {doDia.map(({ c, s }, i) => {
            const open = aberto === c.id;
            return (
              <li key={c.id} className={"contato-card" + (open ? " aberto" : "")} onClick={() => setAberto(open ? null : c.id)}>
                <span className={"contato-coin coin-" + FXKEY[c.faixa]}>{dia * porDia + i + 1}</span>
                <div className="contato-info">
                  <div className="contato-topo">
                    <span className="contato-nome">{c.nome}</span>
                    <span className={prioClasse(s.prioridade)}>{s.prioridade}</span>
                  </div>
                  <div className="contato-tags">
                    <span className={"chip " + FAIXA_CHIP[c.faixa]}><span className={"dot " + FAIXA_DOT[c.faixa]} />{c.faixa}</span>
                    {c.emRisco && <span className="chip chip-risk"><span className="dot dot-risk" />conta grande</span>}
                    <span className="contato-tempo">{recenciaTexto(c.recencia)} sem comprar</span>
                  </div>
                  <div className="contato-foot">
                    <span className="tel-chip">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3.1-8.7A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.7a2 2 0 0 1-.5 2.1L8 9.6a16 16 0 0 0 6 6l1.1-1.1a2 2 0 0 1 2.1-.5c.9.3 1.8.5 2.7.6a2 2 0 0 1 1.7 2z" />
                      </svg>
                      {telefoneFmt(c.telefone) || <span className="sem-tel">sem telefone</span>}
                    </span>
                    <span className="contato-valor">R$ {(c.fat || 0).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} <small>histórico</small></span>
                  </div>
                  {open && (
                    <div className="contato-script">
                      <b>{s.objetivo}</b>
                      <p>{s.script}</p>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
