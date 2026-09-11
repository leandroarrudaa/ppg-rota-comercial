import { useMemo, useState } from "react";
import VisitasView from "./VisitasView";
import ContatoView from "./ContatoView";
import { FAIXAS, num } from "../lib/format";

const FXKEY = { Ouro: "gold", Prata: "silver", Bronze: "bronze" };
const NOTAS_RFM = [1, 2, 3, 4, 5];
const RFM_PADRAO = { rMin: 1, rMax: 5, fMin: 1, fMax: 5, mMin: 1, mMax: 5 };

export default function PlanoView({
  clientes, usuario, aoAbrirRotaDoDia,
  aoAtualizarCliente, visitaPendente, aoIniciarVisita, aoFinalizarVisita, aoCancelarVisita,
}) {
  const [sub, setSub] = useState("Visitas");
  const [meses, setMeses] = useState(6); // "ativo" = comprou nos últimos N meses
  const [faturamentoMin, setFaturamentoMin] = useState(0);
  const [ramo, setRamo] = useState(""); // cnae (ramo de atividade), vazio = todos
  const [faixasOn, setFaixasOn] = useState({ Ouro: true, Prata: true, Bronze: true });
  const [rfm, setRfm] = useState(RFM_PADRAO);
  // Matriz RFM começa escondida — é o filtro mais avançado e o menos usado
  // no dia a dia; abrir só quando o gerente pedir mantém a barra principal
  // enxuta (era isso que ficava "esquisito": tudo sempre aberto, alturas
  // diferentes, a fileira toda desalinhada).
  const [avancadoAberto, setAvancadoAberto] = useState(false);
  // Só importa no mobile (CSS): no desktop os filtros continuam sempre
  // visíveis, independente desse estado — ver .btn-toggle-filtros-claro.
  const [filtrosMobileAbertos, setFiltrosMobileAbertos] = useState(false);

  // Ramos distintos presentes na carteira carregada — só clientes antigos
  // enriquecidos por CNPJ têm essa informação (cadastro manual em campo não tem).
  const ramos = useMemo(() => {
    const vistos = new Set();
    for (const c of clientes) {
      if (c.cnae) vistos.add(c.cnae);
    }
    return [...vistos].sort((a, b) => a.localeCompare(b, "pt-BR"));
  }, [clientes]);

  const faixaPadrao = FAIXAS.every((f) => faixasOn[f]);
  const rfmPadrao = Object.keys(RFM_PADRAO).every((k) => rfm[k] === RFM_PADRAO[k]);
  const temFiltro = faturamentoMin > 0 || ramo || !faixaPadrao || !rfmPadrao;

  const clientesFiltrados = useMemo(() => {
    if (!temFiltro) return clientes;
    return clientes.filter((c) => {
      if (faturamentoMin > 0 && (c.fat || 0) < faturamentoMin) return false;
      if (ramo && c.cnae !== ramo) return false;
      if (c.faixa && !faixasOn[c.faixa]) return false;
      if (!rfmPadrao) {
        if (c.R == null || c.R < rfm.rMin || c.R > rfm.rMax) return false;
        if (c.F == null || c.F < rfm.fMin || c.F > rfm.fMax) return false;
        if (c.M == null || c.M < rfm.mMin || c.M > rfm.mMax) return false;
      }
      return true;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientes, faturamentoMin, ramo, faixasOn, rfm, temFiltro]);

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

  function limparFiltros() {
    setFaturamentoMin(0);
    setRamo("");
    setFaixasOn({ Ouro: true, Prata: true, Bronze: true });
    setRfm(RFM_PADRAO);
  }

  // Atalho pro perfil que o gerente descreveu: comprou um valor legal (M
  // alto), mas faz tempo que não volta (R baixo) e sempre comprou pouco (F
  // baixo) — cliente com potencial que a carteira está deixando esfriar.
  // Nota: R baixo empurra esse cliente pro Plano de Contato, não pro de
  // Visitas (ver aviso abaixo) — é o comportamento esperado, não um bug.
  function aplicarPresetPotencial() {
    setAvancadoAberto(true);
    setRfm({ rMin: 1, rMax: 2, fMin: 1, fMax: 2, mMin: 4, mMax: 5 });
  }

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
        <button
          type="button"
          className="btn-toggle-filtros-claro"
          onClick={() => setFiltrosMobileAbertos((v) => !v)}
        >
          {filtrosMobileAbertos ? "▲ Fechar filtros" : `▾ Filtros${temFiltro ? " · ativos" : ""}`}
        </button>

        <div className={"plano-filtros-corpo" + (filtrosMobileAbertos ? " aberto" : "")}>
        <div className="plano-filtros-linha">
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

          <div className="filtro-grupo">
            <span className="filtro-titulo">Faixa RFM</span>
            <div className="faixa-chips">
              {FAIXAS.map((f) => {
                const k = FXKEY[f];
                const qtd = clientesFiltrados.filter((c) => c.faixa === f).length;
                return (
                  <button
                    key={f}
                    type="button"
                    className={"faixa-chip faixa-chip-" + k + (faixasOn[f] ? "" : " off")}
                    onClick={() => setFaixasOn((s) => ({ ...s, [f]: !s[f] }))}
                    aria-pressed={faixasOn[f]}
                    title={faixasOn[f] ? `Tirar ${f} do plano` : `Incluir ${f} de novo`}
                  >
                    <span className={"coin coin-" + k} />
                    {f} <b>{num(qtd)}</b>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="filtro-grupo">
            <span className="filtro-titulo">&nbsp;</span>
            <button
              type="button"
              className={"btn btn-ghost" + (!rfmPadrao ? " btn-com-filtro" : "")}
              onClick={() => setAvancadoAberto((v) => !v)}
            >
              {avancadoAberto ? "▲ Menos filtros" : "▾ Matriz RFM (R · F · M)"}
              {!rfmPadrao && <span className="ponto-ativo" title="Matriz RFM com filtro aplicado" />}
            </button>
          </div>

          {temFiltro && (
            <div className="filtro-grupo plano-filtros-limpar">
              <span className="filtro-titulo">&nbsp;</span>
              <button className="btn btn-ghost" onClick={limparFiltros}>Limpar filtros</button>
            </div>
          )}
        </div>

        {avancadoAberto && (
          <div className="plano-filtros-rfm">
            <p className="muted" style={{ fontSize: 12.5, margin: 0 }}>
              R = recência, F = frequência, M = valor — notas de 1 (pior) a 5 (melhor) dentro da carteira.
              Atenção: <b>R baixo</b> significa que o cliente já faz tempo que não compra, então ele tende a
              cair no <b>Plano de Contato</b>, não no de Visitas — é esperado o Plano de Visitas zerar se você
              filtrar só R baixo.
            </p>
            <div className="rfm-linhas">
              <div className="rfm-linha">
                <span className="rfm-label">Recência (R)</span>
                <select className="input rfm-select" value={rfm.rMin} onChange={(e) => setRfm((s) => ({ ...s, rMin: +e.target.value }))}>
                  {NOTAS_RFM.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
                <span className="faint">até</span>
                <select className="input rfm-select" value={rfm.rMax} onChange={(e) => setRfm((s) => ({ ...s, rMax: +e.target.value }))}>
                  {NOTAS_RFM.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </div>
              <div className="rfm-linha">
                <span className="rfm-label">Frequência (F)</span>
                <select className="input rfm-select" value={rfm.fMin} onChange={(e) => setRfm((s) => ({ ...s, fMin: +e.target.value }))}>
                  {NOTAS_RFM.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
                <span className="faint">até</span>
                <select className="input rfm-select" value={rfm.fMax} onChange={(e) => setRfm((s) => ({ ...s, fMax: +e.target.value }))}>
                  {NOTAS_RFM.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </div>
              <div className="rfm-linha">
                <span className="rfm-label">Valor (M)</span>
                <select className="input rfm-select" value={rfm.mMin} onChange={(e) => setRfm((s) => ({ ...s, mMin: +e.target.value }))}>
                  {NOTAS_RFM.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
                <span className="faint">até</span>
                <select className="input rfm-select" value={rfm.mMax} onChange={(e) => setRfm((s) => ({ ...s, mMax: +e.target.value }))}>
                  {NOTAS_RFM.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </div>
            </div>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ fontSize: 12, padding: "0.4rem 0.7rem", alignSelf: "flex-start" }}
              onClick={aplicarPresetPotencial}
              title="R até 2 (sumiu) · F até 2 (compra raro) · M de 4 a 5 (quando compra, compra bem) — aparece no Plano de Contato"
            >
              Potencial esquecido: comprou bem, sumiu, é raro
            </button>
          </div>
        )}
        </div>
      </div>

      <div className="plano-corpo">
        {sub === "Visitas"
          ? <VisitasView clientes={ativos} usuario={usuario} aoAbrirRotaDoDia={aoAbrirRotaDoDia} />
          : (
            <ContatoView
              clientes={adormecidos}
              usuario={usuario}
              aoAtualizarCliente={aoAtualizarCliente}
              visitaPendente={visitaPendente}
              aoIniciarVisita={aoIniciarVisita}
              aoFinalizarVisita={aoFinalizarVisita}
              aoCancelarVisita={aoCancelarVisita}
            />
          )}
      </div>
    </div>
  );
}
