import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { gerarPdfRelatorio } from "../lib/pdf";
import { baixarCsv } from "../lib/csv";
import { dataHoraUtc, dataTexto, duracaoTexto, isoLocal } from "../lib/format";

const PRESETS = [
  { chave: "hoje", rotulo: "Hoje" },
  { chave: "ontem", rotulo: "Ontem" },
  { chave: "semana", rotulo: "Esta semana" },
  { chave: "mes", rotulo: "Este mês" },
];

const ABAS = [
  { id: "visitas", rotulo: "Visitas", tipo: "presencial", vazio: "Nenhuma visita finalizada nesse período." },
  { id: "contato", rotulo: "Contato", tipo: "contato", vazio: "Nenhum contato finalizado nesse período." },
];

const ROTULOS_MOTIVO_INSUCESSO = {
  ausente: "cliente ausente",
  endereco_nao_encontrado: "endereço não confere",
  recusou_atendimento: "recusou atendimento",
  nao_atendeu: "não atendeu",
  numero_invalido: "número errado ou não existe",
  recusou_conversa: "recusou conversar",
  outro: "outro motivo",
};

const MOTIVOS_INSUCESSO_VISITA = [
  { valor: "ausente", rotulo: "Cliente ausente" },
  { valor: "endereco_nao_encontrado", rotulo: "Endereço não confere" },
  { valor: "recusou_atendimento", rotulo: "Recusou atendimento" },
  { valor: "outro", rotulo: "Outro" },
];
const MOTIVOS_INSUCESSO_CONTATO = [
  { valor: "nao_atendeu", rotulo: "Não atendeu" },
  { valor: "numero_invalido", rotulo: "Número errado ou não existe" },
  { valor: "recusou_conversa", rotulo: "Recusou conversar" },
  { valor: "outro", rotulo: "Outro" },
];

const ROTULO_ORIGEM = { antigo: "Antigo", novo: "Novo" };

// Constrói a data a partir dos componentes (ano, mês, dia) — evita o
// construtor Date(stringSóDeData), que interpreta como meia-noite UTC e
// mostra o dia anterior pra quem está no Brasil (ver lib/format.js).
function dataDeChaveLocal(chaveDia) {
  const [y, m, d] = chaveDia.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function limitesDoPreset(chave) {
  const hoje = new Date();
  if (chave === "hoje") return [hoje, hoje];
  if (chave === "ontem") {
    const ontem = new Date(hoje);
    ontem.setDate(ontem.getDate() - 1);
    return [ontem, ontem];
  }
  if (chave === "semana") {
    const diaSemana = hoje.getDay(); // 0 = domingo
    const seg = new Date(hoje);
    seg.setDate(seg.getDate() - (diaSemana === 0 ? 6 : diaSemana - 1));
    return [seg, hoje];
  }
  // "mes"
  const dia1 = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
  return [dia1, hoje];
}

export default function RelatoriosView({ usuario }) {
  const ehAdmin = usuario.papel === "admin";
  const [aba, setAba] = useState("visitas");
  const abaAtual = ABAS.find((a) => a.id === aba);
  const [presetAtivo, setPresetAtivo] = useState("semana");
  const [inicioStr, setInicioStr] = useState(() => isoLocal(limitesDoPreset("semana")[0]));
  const [fimStr, setFimStr] = useState(() => isoLocal(limitesDoPreset("semana")[1]));
  const [vendedorId, setVendedorId] = useState("");
  const [vendedores, setVendedores] = useState(null);
  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");
  const [gerandoPdf, setGerandoPdf] = useState(false);
  // Correção do "deu certo?" de uma visita já finalizada, direto no card —
  // edicao guarda { id, sucesso, motivo } só da visita aberta pra edição.
  const [edicao, setEdicao] = useState(null);
  const [salvandoEdicao, setSalvandoEdicao] = useState(false);
  const [erroEdicao, setErroEdicao] = useState("");

  useEffect(() => {
    if (!ehAdmin) return;
    api.get("/api/auth/usuarios").then(setVendedores).catch(() => setVendedores([]));
  }, [ehAdmin]);

  useEffect(() => {
    if (!inicioStr || !fimStr) return;
    setCarregando(true);
    setErro("");
    const params = new URLSearchParams({ inicio: inicioStr, fim: fimStr });
    if (ehAdmin && vendedorId) params.set("vendedorId", vendedorId);
    api.get(`/api/relatorios/visitas?${params}`)
      .then(setDados)
      .catch((e) => { setDados(null); setErro(e.message); })
      .finally(() => setCarregando(false));
  }, [inicioStr, fimStr, vendedorId, ehAdmin]);

  function aplicarPreset(chave) {
    const [ini, fim] = limitesDoPreset(chave);
    setPresetAtivo(chave);
    setInicioStr(isoLocal(ini));
    setFimStr(isoLocal(fim));
  }

  // A API traz visita e contato juntos no período — cada aba filtra o que
  // já veio, sem precisar de uma requisição por aba.
  const visitasDaAba = useMemo(() => {
    if (!dados) return [];
    return dados.visitas.filter((v) => v.tipo === abaAtual.tipo);
  }, [dados, abaAtual]);

  // Efetividade, motivo de insucesso e afins são calculados aqui (não vêm do
  // backend) porque dependem de qual aba está aberta — visita e contato têm
  // efetividades diferentes e o resumo do backend não separa por tipo.
  const resumoAba = useMemo(() => {
    const lista = visitasDaAba;
    const comSucesso = lista.filter((v) => v.sucesso).length;
    const duracoes = lista.filter((v) => v.duracaoMin != null).map((v) => v.duracaoMin);
    const porMotivo = new Map();
    for (const v of lista) {
      if (!v.sucesso) {
        const chave = v.motivoInsucesso || "outro";
        porMotivo.set(chave, (porMotivo.get(chave) || 0) + 1);
      }
    }
    return {
      total: lista.length,
      comSucesso,
      semSucesso: lista.length - comSucesso,
      efetividade: lista.length ? Math.round((comSucesso / lista.length) * 100) : null,
      clientesUnicos: new Set(lista.map((v) => v.clienteId)).size,
      duracaoMediaMin: duracoes.length ? Math.round(duracoes.reduce((a, b) => a + b, 0) / duracoes.length) : null,
      retornosAgendados: lista.filter((v) => v.retornoData).length,
      porMotivo: [...porMotivo.entries()].sort((a, b) => b[1] - a[1]),
    };
  }, [visitasDaAba]);

  // Agrupa por dia de calendário LOCAL do instante de início (não a data UTC
  // ingênua que vem da API) — dataHoraUtc marca o fuso certo antes de ler os
  // componentes locais, senão uma visita perto da meia-noite cai no dia errado.
  const grupos = useMemo(() => {
    const porDia = new Map();
    for (const v of visitasDaAba) {
      const chave = isoLocal(dataHoraUtc(v.inicio));
      if (!porDia.has(chave)) porDia.set(chave, []);
      porDia.get(chave).push(v);
    }
    return [...porDia.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }, [visitasDaAba]);

  const nomeVendedorFiltrado = ehAdmin && vendedorId
    ? vendedores?.find((v) => String(v.id) === vendedorId)?.nome
    : null;

  function baixarPdf() {
    if (visitasDaAba.length === 0) return;
    setGerandoPdf(true);
    const tituloPeriodo = `${dataTexto(inicioStr)} a ${dataTexto(fimStr)}`
      + (nomeVendedorFiltrado ? ` · ${nomeVendedorFiltrado}` : "");
    const resumoPdf = {
      totalVisitas: resumoAba.total,
      clientesUnicos: resumoAba.clientesUnicos,
      duracaoMediaMin: resumoAba.duracaoMediaMin,
      retornosAgendados: resumoAba.retornosAgendados,
    };
    gerarPdfRelatorio({ tituloPeriodo, resumo: resumoPdf, visitas: visitasDaAba })
      .finally(() => setGerandoPdf(false));
  }

  // CSV pro Rafael apurar comissão: só visita com sucesso conta CNPJ — quem
  // não recebeu o Taborda ou não atendeu não gera comissão (ver memória do
  // relatório de comissão).
  function baixarCsvVisitas() {
    const linhas = visitasDaAba.filter((v) => v.sucesso);
    baixarCsv(
      `visitas-comissao_${inicioStr}_a_${fimStr}.csv`,
      [
        { rotulo: "CNPJ", valor: (v) => v.clienteCnpj || "" },
        { rotulo: "Código do cliente", valor: (v) => v.clienteCodigoErp || "" },
        { rotulo: "Cliente", valor: (v) => v.clienteNome },
        { rotulo: "Data", valor: (v) => dataTexto(isoLocal(dataHoraUtc(v.inicio))) },
        { rotulo: "Vendedor", valor: (v) => v.vendedorNome },
        { rotulo: "Novo ou antigo", valor: (v) => ROTULO_ORIGEM[v.clienteOrigem] || "" },
      ],
      linhas,
    );
  }

  // CSV de contato traz sucesso e insucesso junto (com o motivo) e a faixa
  // RFM — é o que ajuda a entender o perfil de quem atende x não atende.
  function baixarCsvContato() {
    baixarCsv(
      `contatos_${inicioStr}_a_${fimStr}.csv`,
      [
        { rotulo: "CNPJ", valor: (v) => v.clienteCnpj || "" },
        { rotulo: "Código do cliente", valor: (v) => v.clienteCodigoErp || "" },
        { rotulo: "Cliente", valor: (v) => v.clienteNome },
        { rotulo: "Data", valor: (v) => dataTexto(isoLocal(dataHoraUtc(v.inicio))) },
        { rotulo: "Vendedor", valor: (v) => v.vendedorNome },
        { rotulo: "Faixa RFM", valor: (v) => v.clienteFaixa || "" },
        { rotulo: "Deu certo?", valor: (v) => (v.sucesso ? "Sim" : "Não") },
        { rotulo: "Motivo", valor: (v) => (v.sucesso ? "" : ROTULOS_MOTIVO_INSUCESSO[v.motivoInsucesso] || v.motivoInsucesso || "") },
        { rotulo: "Observação", valor: (v) => v.observacao || "" },
      ],
      visitasDaAba,
    );
  }

  // CSV completo de visita: traz sucesso E insucesso, com motivo e a
  // observação de texto livre — é o que mostra padrões tipo "casa não é
  // empresa" que o CSV de comissão (só sucesso) não capta.
  function baixarCsvVisitasCompleto() {
    baixarCsv(
      `visitas-completo_${inicioStr}_a_${fimStr}.csv`,
      [
        { rotulo: "CNPJ", valor: (v) => v.clienteCnpj || "" },
        { rotulo: "Código do cliente", valor: (v) => v.clienteCodigoErp || "" },
        { rotulo: "Cliente", valor: (v) => v.clienteNome },
        { rotulo: "Data", valor: (v) => dataTexto(isoLocal(dataHoraUtc(v.inicio))) },
        { rotulo: "Vendedor", valor: (v) => v.vendedorNome },
        { rotulo: "Novo ou antigo", valor: (v) => ROTULO_ORIGEM[v.clienteOrigem] || "" },
        { rotulo: "Deu certo?", valor: (v) => (v.sucesso ? "Sim" : "Não") },
        { rotulo: "Motivo", valor: (v) => (v.sucesso ? "" : ROTULOS_MOTIVO_INSUCESSO[v.motivoInsucesso] || v.motivoInsucesso || "") },
        { rotulo: "Observação", valor: (v) => v.observacao || "" },
      ],
      visitasDaAba,
    );
  }

  const motivosDaAba = aba === "visitas" ? MOTIVOS_INSUCESSO_VISITA : MOTIVOS_INSUCESSO_CONTATO;

  function iniciarEdicao(v) {
    setErroEdicao("");
    setEdicao({ id: v.id, sucesso: v.sucesso, motivo: v.motivoInsucesso || motivosDaAba[0].valor });
  }

  async function salvarEdicao() {
    if (!edicao) return;
    setSalvandoEdicao(true);
    setErroEdicao("");
    try {
      const atualizado = await api.patch(`/api/visitas/${edicao.id}/resultado`, {
        sucesso: edicao.sucesso,
        motivoInsucesso: edicao.sucesso ? null : edicao.motivo,
      });
      setDados((prev) => ({
        ...prev,
        visitas: prev.visitas.map((v) =>
          v.id === edicao.id ? { ...v, sucesso: atualizado.sucesso, motivoInsucesso: atualizado.motivoInsucesso } : v
        ),
      }));
      setEdicao(null);
    } catch (e) {
      setErroEdicao(e.message);
    } finally {
      setSalvandoEdicao(false);
    }
  }

  return (
    <div className="mapa-layout contato-layout">
      <aside className="painel painel-largo">
        <div className="painel-head">
          <h3>Relatórios</h3>
          <p className="muted" style={{ fontSize: 13 }}>
            {ehAdmin ? "O que o time fez, por período" : "Suas visitas, por período"}
          </p>
        </div>

        <div className="subtabs">
          {ABAS.map((a) => (
            <button
              key={a.id}
              className={"subtab" + (aba === a.id ? " on" : "")}
              onClick={() => setAba(a.id)}
            >
              {a.rotulo}
            </button>
          ))}
        </div>

        <div className="filtro-grupo">
          <span className="filtro-titulo">Período</span>
          <div className="periodo-btns">
            {PRESETS.map((p) => (
              <button
                key={p.chave}
                className={"dia-btn" + (presetAtivo === p.chave ? " on" : "")}
                onClick={() => aplicarPreset(p.chave)}
              >
                {p.rotulo}
              </button>
            ))}
          </div>
        </div>

        <div className="filtro-grupo">
          <span className="filtro-titulo">Personalizado</span>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              className="input" type="date" value={inicioStr}
              onChange={(e) => { setInicioStr(e.target.value); setPresetAtivo(null); }}
            />
            <input
              className="input" type="date" value={fimStr}
              onChange={(e) => { setFimStr(e.target.value); setPresetAtivo(null); }}
            />
          </div>
        </div>

        {ehAdmin && (
          <div className="filtro-grupo">
            <span className="filtro-titulo">Vendedor</span>
            <select className="input" value={vendedorId} onChange={(e) => setVendedorId(e.target.value)}>
              <option value="">Todo o time</option>
              {(vendedores || []).map((v) => (
                <option key={v.id} value={v.id}>{v.nome}</option>
              ))}
            </select>
          </div>
        )}

        <div className="resumo">
          <div className="resumo-item"><span>{aba === "visitas" ? "Visitas feitas" : "Contatos feitos"}</span><b>{dados ? resumoAba.total : "—"}</b></div>
          <div className="resumo-item destaque"><span>Deram certo</span><b>{dados ? `${resumoAba.comSucesso} (${resumoAba.efetividade ?? 0}%)` : "—"}</b></div>
          <div className="resumo-item"><span>Não deram certo</span><b>{dados ? resumoAba.semSucesso : "—"}</b></div>
          <div className="resumo-item"><span>Clientes únicos</span><b>{dados ? resumoAba.clientesUnicos : "—"}</b></div>
          <div className="resumo-item"><span>Duração média</span><b>{dados ? duracaoTexto(resumoAba.duracaoMediaMin) : "—"}</b></div>
          <div className="resumo-item"><span>Retornos agendados</span><b>{dados ? resumoAba.retornosAgendados : "—"}</b></div>
        </div>

        {aba === "contato" && resumoAba.porMotivo.length > 0 && (
          <div className="filtro-grupo">
            <span className="filtro-titulo">Por que não deu certo</span>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {resumoAba.porMotivo.map(([motivo, qtd]) => (
                <div key={motivo} className="resumo-item" style={{ padding: "4px 0" }}>
                  <span>{ROTULOS_MOTIVO_INSUCESSO[motivo] || motivo}</span><b>{qtd}</b>
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          className="btn btn-primary"
          style={{ width: "100%", justifyContent: "center" }}
          disabled={visitasDaAba.length === 0 || gerandoPdf}
          onClick={baixarPdf}
        >
          {gerandoPdf ? "Gerando…" : "Baixar PDF do período"}
        </button>
        <button
          className="btn btn-ghost"
          style={{ width: "100%", justifyContent: "center", marginTop: 8 }}
          disabled={aba === "visitas" ? resumoAba.comSucesso === 0 : visitasDaAba.length === 0}
          onClick={aba === "visitas" ? baixarCsvVisitas : baixarCsvContato}
        >
          {aba === "visitas" ? "Baixar CSV para comissão" : "Baixar CSV"}
        </button>
        {aba === "visitas" && (
          <button
            className="btn btn-ghost"
            style={{ width: "100%", justifyContent: "center", marginTop: 8 }}
            disabled={visitasDaAba.length === 0}
            onClick={baixarCsvVisitasCompleto}
          >
            Baixar CSV completo (com observação)
          </button>
        )}
      </aside>

      <div className="contato-lista-wrap">
        {erro && <div className="login-erro" style={{ maxWidth: 800, margin: "0 auto 16px" }}>{erro}</div>}
        {carregando ? (
          <p className="muted" style={{ textAlign: "center" }}>Carregando…</p>
        ) : visitasDaAba.length === 0 ? (
          <div className="vazio">
            <p>{abaAtual.vazio}</p>
          </div>
        ) : (
          <div style={{ maxWidth: 800, margin: "0 auto", display: "flex", flexDirection: "column", gap: 22 }}>
            {grupos.map(([chaveDia, visitasDoDia]) => (
              <div key={chaveDia}>
                <h4 className="relatorio-dia-titulo">
                  {dataDeChaveLocal(chaveDia).toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" })}
                  <span className="faint" style={{ fontWeight: 500, marginLeft: 8 }}>
                    {visitasDoDia.length} {aba === "visitas" ? "visita" : "contato"}{visitasDoDia.length > 1 ? "s" : ""}
                  </span>
                </h4>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {visitasDoDia.map((v) => (
                    <div key={v.id} className="cliente-card relatorio-card">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
                        <b>{v.clienteNome}</b>
                        <span className="faint" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                          {dataHoraUtc(v.inicio).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                          {" · "}{duracaoTexto(v.duracaoMin)}
                        </span>
                      </div>
                      <p className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                        {v.clienteCnpj || "sem CNPJ"}{v.clienteCodigoErp ? ` · código ${v.clienteCodigoErp}` : ""}
                        {v.clienteCidade ? ` · ${v.clienteCidade}` : ""}{ehAdmin ? ` · ${v.vendedorNome}` : ""}
                      </p>
                      {v.observacao && <p style={{ fontSize: 13, marginTop: 8 }}>{v.observacao}</p>}
                      {edicao?.id === v.id ? (
                        <div className="edicao-resultado">
                          <button
                            type="button"
                            className={"chip chip-ok" + (edicao.sucesso ? " on" : "")}
                            onClick={() => setEdicao((e) => ({ ...e, sucesso: true }))}
                          >
                            ✓ Deu certo
                          </button>
                          <button
                            type="button"
                            className={"chip chip-erro" + (!edicao.sucesso ? " on" : "")}
                            onClick={() => setEdicao((e) => ({ ...e, sucesso: false }))}
                          >
                            ✗ Sem sucesso
                          </button>
                          {!edicao.sucesso && (
                            <select
                              className="input"
                              value={edicao.motivo}
                              onChange={(ev) => setEdicao((e) => ({ ...e, motivo: ev.target.value }))}
                            >
                              {motivosDaAba.map((m) => (
                                <option key={m.valor} value={m.valor}>{m.rotulo}</option>
                              ))}
                            </select>
                          )}
                          <button className="btn btn-primary" disabled={salvandoEdicao} onClick={salvarEdicao}>
                            {salvandoEdicao ? "Salvando…" : "Salvar"}
                          </button>
                          <button className="btn btn-ghost" disabled={salvandoEdicao} onClick={() => setEdicao(null)}>
                            Cancelar
                          </button>
                          {erroEdicao && <span className="login-erro" style={{ fontSize: 12 }}>{erroEdicao}</span>}
                        </div>
                      ) : (
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                          {v.sucesso ? (
                            <span className="chip chip-ok chip-editavel" onClick={() => iniciarEdicao(v)} title="Clique para corrigir">
                              ✓ Deu certo
                            </span>
                          ) : (
                            <span className="chip chip-erro chip-editavel" onClick={() => iniciarEdicao(v)} title="Clique para corrigir">
                              ✗ Sem sucesso{v.motivoInsucesso ? ` — ${ROTULOS_MOTIVO_INSUCESSO[v.motivoInsucesso] || v.motivoInsucesso}` : ""}
                            </span>
                          )}
                          {v.retornoData && (
                            <span className="chip chip-gold">Retorno {dataTexto(v.retornoData)}</span>
                          )}
                          {v.promessas.map((p) => (
                            <span key={p.id} className="chip chip-motivo" title={p.texto}>
                              🎁 {p.cumprida ? "cumprida" : "pendente"}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
