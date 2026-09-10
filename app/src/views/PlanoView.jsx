import { useMemo, useState } from "react";
import VisitasView from "./VisitasView";
import ContatoView from "./ContatoView";

export default function PlanoView({ clientes, usuario, aoAbrirRotaDoDia }) {
  const [sub, setSub] = useState("Visitas");
  const [meses, setMeses] = useState(6); // "ativo" = comprou nos últimos N meses
  const [faturamentoMin, setFaturamentoMin] = useState(0);
  const [ramo, setRamo] = useState(""); // cnae (ramo de atividade), vazio = todos

  // Ramos distintos presentes na carteira carregada — só clientes antigos
  // enriquecidos por CNPJ têm essa informação (cadastro manual em campo não tem).
  const ramos = useMemo(() => {
    const vistos = new Set();
    for (const c of clientes) {
      if (c.cnae) vistos.add(c.cnae);
    }
    return [...vistos].sort((a, b) => a.localeCompare(b, "pt-BR"));
  }, [clientes]);

  const clientesFiltrados = useMemo(() => {
    if (faturamentoMin <= 0 && !ramo) return clientes;
    return clientes.filter((c) => {
      if (faturamentoMin > 0 && (c.fat || 0) < faturamentoMin) return false;
      if (ramo && c.cnae !== ramo) return false;
      return true;
    });
  }, [clientes, faturamentoMin, ramo]);

  const { ativos, adormecidos } = useMemo(() => {
    const corte = meses * 30;
    const ativos = [];
    const adormecidos = [];
    for (const c of clientesFiltrados) {
      if (c.recencia == null) continue;
      if (c.recencia <= corte) ativos.push(c);
      else adormecidos.push(c);
    }
    return { ativos, adormecidos };
  }, [clientesFiltrados, meses]);

  const temFiltro = faturamentoMin > 0 || ramo;

  return (
    <div className="plano-wrap">
      <div className="subtabs-bar">
        <div className="subtabs">
          <button className={"subtab" + (sub === "Visitas" ? " on" : "")} onClick={() => setSub("Visitas")}>
            Plano de Visitas <b>{ativos.length}</b>
          </button>
          <button className={"subtab" + (sub === "Contato" ? " on" : "")} onClick={() => setSub("Contato")}>
            Plano de Contato <b>{adormecidos.length}</b>
          </button>
        </div>

        <div className="corte">
          <span className="faint">Considera ativo quem comprou nos últimos</span>
          <input
            type="range" min="2" max="18" value={meses}
            onChange={(e) => setMeses(+e.target.value)}
            className="slider corte-slider"
          />
          <b>{meses} meses</b>
        </div>
      </div>

      <div className="plano-filtros">
        <div className="filtro-grupo">
          <span className="filtro-titulo">Faturamento mínimo</span>
          <input
            className="input"
            type="number"
            min="0"
            step="1000"
            placeholder="Ex: 30000"
            value={faturamentoMin || ""}
            onChange={(e) => setFaturamentoMin(Number(e.target.value) || 0)}
          />
        </div>

        {ramos.length > 0 && (
          <div className="filtro-grupo">
            <span className="filtro-titulo">Ramo de atividade</span>
            <select className="input" value={ramo} onChange={(e) => setRamo(e.target.value)}>
              <option value="">Todos os ramos</option>
              {ramos.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        )}

        {temFiltro && (
          <button className="btn btn-ghost" onClick={() => { setFaturamentoMin(0); setRamo(""); }}>
            Limpar filtros
          </button>
        )}
      </div>

      <div className="plano-corpo">
        {sub === "Visitas"
          ? <VisitasView clientes={ativos} usuario={usuario} aoAbrirRotaDoDia={aoAbrirRotaDoDia} />
          : <ContatoView clientes={adormecidos} />}
      </div>
    </div>
  );
}
