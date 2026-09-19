import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { brl, telefoneFmt } from "../lib/format";

const ProspeccaoImportar = lazy(() => import("./ProspeccaoImportar"));

const TAMANHO_PAGINA = 50;
const CIDADE_PADRAO = "PONTA GROSSA";

// ascPadrao: texto começa em A-Z; número começa do maior — é o que se quer ver
// primeiro. Mesma regra das outras tabelas do app.
const COLUNAS = [
  { campo: "razaoSocial", rotulo: "Empresa", ascPadrao: true },
  { campo: "notaPotencial", rotulo: "Potencial", ascPadrao: false, num: true,
    ajuda: "Nota de 0 a 100 de quão bom candidato a cliente ouro: ramo, estrutura e capital. Passe o mouse na nota para ver como foi montada." },
  { campo: "ramo", rotulo: "Ramo", ascPadrao: true },
  { campo: "porte", rotulo: "Porte", ascPadrao: true },
  { campo: "capitalSocial", rotulo: "Capital social", ascPadrao: false, num: true },
  { campo: "bairro", rotulo: "Bairro", ascPadrao: true },
  { campo: "telefone", rotulo: "Telefone", ascPadrao: true },
  { campo: "situacaoReceita", rotulo: "Receita", ascPadrao: true,
    ajuda: "Situação conferida na Receita. \"Não conferida\" = ainda não consultamos (a lista diz ATIVA para todos, mas é uma foto antiga)." },
  { campo: "socios", rotulo: "Sócios", ascPadrao: true, ajuda: "Quem provavelmente decide a compra (vem da Receita)" },
];

const COLUNAS_RAMOS = [
  { campo: "ramo", rotulo: "Ramo", ascPadrao: true },
  { campo: "empresas", rotulo: "Empresas", num: true },
  { campo: "micro", rotulo: "Micro", num: true },
  { campo: "pequena", rotulo: "Pequena", num: true },
  { campo: "demais", rotulo: "Média/grande", num: true, ajuda: "Porte \"Demais\" na Receita: fora do Simples" },
  { campo: "total", rotulo: "Total com MEI", num: true },
];

const FILTROS_INICIAIS = {
  busca: "", ramo: "", tipo: "empresa", porte: "", situacao: "", notaMin: 0, ordenar: "notaPotencial", direcao: "desc",
};

function SituacaoReceita({ valor }) {
  if (!valor) return <span className="faint">não conferida</span>;
  if (valor === "ATIVA") return <span>✓ Ativa</span>;
  const rotulo = valor === "NAO_ENCONTRADO" ? "Não encontrada" : valor.charAt(0) + valor.slice(1).toLowerCase();
  return <span className="chip chip-risk">{rotulo}</span>;
}

const n = (v) => (v ?? 0).toLocaleString("pt-BR");

function cnpjFmt(c) {
  const d = String(c || "").replace(/\D/g, "");
  return d.length === 14 ? d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5") : c;
}

function Numero({ rotulo, valor, destaque, ajuda }) {
  return (
    <div className={"previa-item" + (destaque ? " destaque" : "")}>
      <span>{rotulo}</span>
      <b>{valor}</b>
      {ajuda && <small className="faint">{ajuda}</small>}
    </div>
  );
}

// Aba de Prospecção (só Admin): empresas que ainda não são clientes, vindas da
// lista importada. Esta primeira versão mostra o tamanho da lista, o que sobra
// por ramo e a lista em si — a prioridade por ramo e a nota entram a seguir.
export default function ProspeccaoView() {
  const [cidade, setCidade] = useState(CIDADE_PADRAO);
  const [resumo, setResumo] = useState(null);
  const [filtros, setFiltros] = useState(FILTROS_INICIAIS);
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");
  const [mostrarImportar, setMostrarImportar] = useState(false);
  const [ordemRamos, setOrdemRamos] = useState({ campo: "empresas", direcao: "desc" });
  const [avisoImportacao, setAvisoImportacao] = useState("");
  // sobe a cada importação: faz a tabela recarregar mesmo quando nenhum filtro mudou
  const [versaoLista, setVersaoLista] = useState(0);
  const [conferencia, setConferencia] = useState(null); // { rodando, ativas, naoAtivas, falhas, restam, mensagem }
  const [selecionados, setSelecionados] = useState(() => new Map()); // id -> nome
  const [levando, setLevando] = useState(null); // { fase, criados, localizados, semLocal, restam, mensagem }

  const carregarResumo = useCallback(() => {
    api.get(`/api/prospectos/resumo?cidade=${encodeURIComponent(cidade)}`)
      .then((r) => {
        setResumo(r);
        // se a cidade padrão não existe na lista (ex.: só Curitiba), mostra tudo
        if (cidade && r.cidades.length > 0 && !r.cidades.some((c) => c.cidade === cidade)) setCidade("");
        if (r.totalNaLista === 0) setMostrarImportar(true);
      })
      .catch((e) => setErro(e.message));
  }, [cidade]);

  useEffect(carregarResumo, [carregarResumo]);

  const temLista = (resumo?.totalNaLista ?? 0) > 0;

  const carregar = useCallback(() => {
    if (!temLista) return;
    setCarregando(true);
    setErro("");
    const params = new URLSearchParams({
      pagina: String(pagina),
      tamanho: String(TAMANHO_PAGINA),
      ordenar: filtros.ordenar,
      direcao: filtros.direcao,
    });
    if (cidade) params.set("cidade", cidade);
    if (filtros.ramo) params.set("ramo", filtros.ramo);
    if (filtros.tipo) params.set("tipo", filtros.tipo);
    if (filtros.porte) params.set("porte", filtros.porte);
    if (filtros.situacao) params.set("situacao", filtros.situacao);
    if (filtros.notaMin > 0) params.set("notaMin", String(filtros.notaMin));
    if (filtros.busca.trim().length >= 2) params.set("busca", filtros.busca.trim());
    api.get(`/api/prospectos?${params}`)
      .then(setDados)
      .catch((e) => { setDados(null); setErro(e.message); })
      .finally(() => setCarregando(false));
  }, [filtros, pagina, cidade, temLista]);

  // espera parar de digitar: cada busca é uma ida ao banco, que fica longe
  useEffect(() => {
    const t = setTimeout(carregar, 300);
    return () => clearTimeout(t);
  }, [carregar, versaoLista]);

  // Confere na Receita, NO SERVIDOR, todas as empresas do filtro que ainda não foram
  // conferidas. A Receita aceita ~100 consultas por minuto; quando pede para esperar, o
  // servidor espera e continua sozinho — pode fechar a página. Aqui só acompanhamos.
  const consultarStatus = useCallback(
    () => api.get("/api/prospectos/conferir-receita/status").then(setConferencia).catch(() => {}),
    []
  );

  useEffect(() => { consultarStatus(); }, [consultarStatus]);

  const conferindo = Boolean(conferencia?.rodando);
  useEffect(() => {
    if (!conferindo) return undefined;
    const t = setInterval(consultarStatus, 3000);
    return () => clearInterval(t);
  }, [conferindo, consultarStatus]);

  // quando a conferência termina (ou é parada), atualiza a lista: quem fechou some
  const estavaConferindo = useRef(false);
  useEffect(() => {
    if (estavaConferindo.current && !conferindo) { carregar(); carregarResumo(); }
    estavaConferindo.current = conferindo;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conferindo]);

  async function conferirNaReceita() {
    setErro("");
    try {
      const corpo = {
        cidade: cidade || null, ramo: filtros.ramo || null, tipo: filtros.tipo || null,
        porte: filtros.porte || null, busca: filtros.busca.trim().length >= 2 ? filtros.busca.trim() : null,
        nota_min: filtros.notaMin > 0 ? filtros.notaMin : null,
      };
      setConferencia(await api.post("/api/prospectos/conferir-receita/iniciar", corpo));
    } catch (e) {
      setErro(e.message);
    }
  }

  async function pararConferencia() {
    try {
      setConferencia(await api.post("/api/prospectos/conferir-receita/parar", {}));
    } catch (e) {
      setErro(e.message);
    }
  }

  function alternarSelecao(p) {
    setSelecionados((s0) => {
      const novo = new Map(s0);
      if (novo.has(p.id)) novo.delete(p.id);
      else novo.set(p.id, p.razaoSocial);
      return novo;
    });
  }

  function alternarPagina() {
    const pagina = dados?.itens || [];
    setSelecionados((s0) => {
      const novo = new Map(s0);
      if (pagina.every((p) => novo.has(p.id))) pagina.forEach((p) => novo.delete(p.id));
      else pagina.forEach((p) => novo.set(p.id, p.razaoSocial));
      return novo;
    });
  }

  // Leva as escolhidas (ou todas as confirmadas ativas do filtro) para a carteira como
  // cliente novo, e em seguida acha cada endereço no mapa, um lote por vez.
  async function levarParaCarteira(todasDoFiltro) {
    if (todasDoFiltro && !window.confirm(
      "Levar para a carteira TODAS as empresas deste filtro que a Receita já confirmou como ativas?\n\n" +
      "Elas viram clientes novos e passam a aparecer no mapa e nos planos.")) return;
    setErro("");
    setLevando({ fase: "levando", criados: 0, localizados: 0, semLocal: 0, restam: 0, mensagem: "" });
    let criados = 0, localizados = 0, semLocal = 0, mensagem = "";
    try {
      const corpo = todasDoFiltro
        ? { todas_do_filtro: true, filtros: {
            cidade: cidade || null, ramo: filtros.ramo || null, tipo: filtros.tipo || null, porte: filtros.porte || null,
            busca: filtros.busca.trim().length >= 2 ? filtros.busca.trim() : null,
            nota_min: filtros.notaMin > 0 ? filtros.notaMin : null } }
        : { ids: [...selecionados.keys()] };
      const r = await api.post("/api/prospectos/levar-para-carteira", corpo);
      criados = r.criados;
      setSelecionados(new Map());
      for (;;) {
        setLevando({ fase: "localizando", criados, localizados, semLocal, restam: 0, mensagem: "" });
        const loc = await api.post("/api/prospectos/localizar", {});
        localizados += loc.localizados; semLocal += loc.semLocal;
        if (loc.restam === 0 || loc.processados === 0) break;
      }
      if (r.acimaDoLimite) mensagem = "Havia mais empresas no filtro. Repita para levar as próximas.";
    } catch (e) {
      mensagem = e.message;
    } finally {
      setLevando({ fase: "fim", criados, localizados, semLocal, restam: 0, mensagem });
      carregar();
      carregarResumo();
    }
  }

  function mudarFiltro(campo, valor) {
    setFiltros((f) => ({ ...f, [campo]: valor }));
    setPagina(1);
  }

  function mudarCidade(valor) {
    setCidade(valor);
    setFiltros((f) => ({ ...f, ramo: "" }));
    setPagina(1);
  }

  // A ordenação vai para o servidor: a lista é paginada, e ordenar só os 50 da
  // tela daria uma ordem falsa sobre milhares de empresas.
  function ordenarPor(coluna) {
    setFiltros((f) => ({
      ...f,
      ordenar: coluna.campo,
      direcao: f.ordenar === coluna.campo ? (f.direcao === "asc" ? "desc" : "asc") : (coluna.ascPadrao ? "asc" : "desc"),
    }));
    setPagina(1);
  }

  function ordenarRamos(coluna) {
    setOrdemRamos((o) => ({
      campo: coluna.campo,
      direcao: o.campo === coluna.campo ? (o.direcao === "asc" ? "desc" : "asc") : (coluna.ascPadrao ? "asc" : "desc"),
    }));
  }

  const ramosOrdenados = useMemo(() => {
    const lista = [...(resumo?.ramos || [])];
    const { campo, direcao } = ordemRamos;
    lista.sort((a, b) => {
      const va = a[campo], vb = b[campo];
      const c = typeof va === "string" ? va.localeCompare(vb, "pt-BR") : va - vb;
      return direcao === "asc" ? c : -c;
    });
    return lista;
  }, [resumo, ordemRamos]);

  const itens = dados?.itens || [];
  const total = dados?.total || 0;
  const paginas = Math.max(1, Math.ceil(total / TAMANHO_PAGINA));

  // Fecha o painel: ele é comprido e, aberto, empurra a lista para baixo da tela —
  // parece que nada apareceu. O resultado fica numa linha curta no topo.
  function aoImportar(r) {
    setMostrarImportar(false);
    setPagina(1);
    setVersaoLista((v) => v + 1);
    if (r) {
      setAvisoImportacao(
        `Importação concluída: ${n(r.novos)} novas, ${n(r.atualizados)} atualizadas, ` +
        `${n(r.jaClientes)} já são clientes, ${n(r.meiAutonomos)} MEI/autônomos.`
      );
    }
    carregarResumo();
  }

  return (
    <div className="gestao">
      <div className="gestao-cabecalho">
        <h3 style={{ margin: 0 }}>Prospecção</h3>
        <p className="muted" style={{ fontSize: 13 }}>
          Empresas que ainda não são clientes, vindas da lista importada. A lista é uma foto antiga e diz
          "ativa" para todo mundo: use <b>Conferir na Receita</b> para saber quem ainda existe. Quem a
          Receita mostrar como fechada some da lista.
        </p>
      </div>

      <div className="gestao-corpo">
        {erro && <div className="login-erro">{erro}</div>}
        {avisoImportacao && <div className="carteira-aviso">{avisoImportacao}</div>}

        <div className="importar-envio" style={{ marginBottom: 8 }}>
          <button className="btn btn-ghost" onClick={() => setMostrarImportar((v) => !v)}>
            {mostrarImportar ? "Fechar importação" : temLista ? "Importar nova lista" : "Importar lista"}
          </button>
          {temLista && (
            <label className="carteira-check" style={{ marginLeft: 12 }}>
              Cidade{" "}
              <select className="input" value={cidade} onChange={(e) => mudarCidade(e.target.value)}>
                <option value="">Todas as cidades</option>
                {resumo.cidades.map((c) => (
                  <option key={c.cidade} value={c.cidade}>{c.cidade} ({n(c.total)})</option>
                ))}
              </select>
            </label>
          )}
        </div>

        {mostrarImportar && (
          <Suspense fallback={<p className="muted">Carregando…</p>}>
            <ProspeccaoImportar aoConcluir={aoImportar} />
          </Suspense>
        )}

        {!temLista && !mostrarImportar && resumo && (
          <p className="muted">Ainda não há nenhuma lista importada.</p>
        )}

        {temLista && (
          <>
            <div className="previa-grade" style={{ margin: "12px 0" }}>
              <Numero rotulo="Na lista" valor={n(resumo.totalNaLista)} />
              <Numero rotulo="Já são clientes" valor={n(resumo.jaClientes)} ajuda="ficam de fora" />
              <Numero
                rotulo={cidade ? `Em ${cidade.toLowerCase().replace(/(^|\s)\S/g, (l) => l.toUpperCase())}` : "Nas cidades"}
                valor={n(resumo.naCidade)}
              />
              <Numero
                rotulo="Empresas (sem MEI)" valor={n(resumo.empresasNaCidade)} destaque
                ajuda="MEI e autônomos identificados pelo nome"
              />
            </div>

            <span className="filtro-titulo">Ramos — clique num ramo para filtrar a lista</span>
            <div className="carteira-tabela-wrap" style={{ marginBottom: 16 }}>
              <table className="carteira-tabela">
                <thead>
                  <tr>
                    {COLUNAS_RAMOS.map((c) => (
                      <th
                        key={c.campo}
                        className={"ordenavel" + (c.num ? " num" : "")}
                        onClick={() => ordenarRamos(c)}
                        title={c.ajuda || "Clique para ordenar"}
                      >
                        {c.rotulo} {ordemRamos.campo === c.campo ? (ordemRamos.direcao === "asc" ? "▲" : "▼") : ""}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ramosOrdenados.map((r) => (
                    <tr
                      key={r.ramo}
                      className={filtros.ramo === r.ramo ? "marcada" : ""}
                      style={{ cursor: "pointer" }}
                      onClick={() => mudarFiltro("ramo", filtros.ramo === r.ramo ? "" : r.ramo)}
                    >
                      <td>{r.ramo}</td>
                      <td className="num"><b>{n(r.empresas)}</b></td>
                      <td className="num">{n(r.micro)}</td>
                      <td className="num">{n(r.pequena)}</td>
                      <td className="num">{n(r.demais)}</td>
                      <td className="num">{n(r.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="carteira-filtros">
              <input
                className="input"
                placeholder="Buscar por nome, CNPJ ou bairro…"
                value={filtros.busca}
                onChange={(e) => mudarFiltro("busca", e.target.value)}
              />
              <select className="input" value={filtros.tipo} onChange={(e) => mudarFiltro("tipo", e.target.value)}>
                <option value="empresa">Só empresas</option>
                <option value="mei_autonomo">Só MEI / autônomos</option>
                <option value="">Empresas e MEI</option>
              </select>
              <select className="input" value={filtros.porte} onChange={(e) => mudarFiltro("porte", e.target.value)}>
                <option value="">Todos os portes</option>
                <option value="Micro">Micro</option>
                <option value="Pequena">Pequena</option>
                <option value="Demais">Média/grande (Demais)</option>
              </select>
              <label className="faint" style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
                Nota mínima
                <input
                  className="input" type="number" min="0" max="100" step="5" style={{ width: 70 }}
                  value={filtros.notaMin || ""} placeholder="0"
                  onChange={(e) => mudarFiltro("notaMin", Math.max(0, Math.min(100, Number(e.target.value) || 0)))}
                />
              </label>
              <select className="input" value={filtros.situacao} onChange={(e) => mudarFiltro("situacao", e.target.value)}>
                <option value="">Ativas e não conferidas</option>
                <option value="ativa">Só confirmadas ativas</option>
                <option value="nao_conferida">Ainda não conferidas</option>
                <option value="nao_ativa">Fechadas / inaptas (escondidas)</option>
              </select>
              <select className="input" value={filtros.ramo} onChange={(e) => mudarFiltro("ramo", e.target.value)}>
                <option value="">Todos os ramos</option>
                {(resumo.ramos || []).map((r) => <option key={r.ramo} value={r.ramo}>{r.ramo}</option>)}
              </select>
              <button className="btn btn-ghost" onClick={() => { setFiltros(FILTROS_INICIAIS); setPagina(1); }}>
                Limpar filtros
              </button>
            </div>

            <div className="carteira-barra">
              <span className="muted" style={{ fontSize: 13 }}>
                {carregando ? "Carregando…" : `${n(total)} ${total === 1 ? "empresa" : "empresas"}`}
                {dados && !carregando && ` · ${n(dados.pendentesConferencia)} ainda não conferidas na Receita`}
              </span>
              <div className="carteira-acoes">
                {selecionados.size > 0 && (
                  <button
                    className="btn btn-primary"
                    disabled={levando && levando.fase !== "fim"}
                    onClick={() => levarParaCarteira(false)}
                  >
                    Levar {selecionados.size} para a carteira
                  </button>
                )}
                <button
                  className="btn btn-ghost"
                  disabled={levando && levando.fase !== "fim"}
                  onClick={() => levarParaCarteira(true)}
                  title="Leva todas as empresas deste filtro que a Receita já confirmou como ativas"
                >
                  Levar todas as confirmadas
                </button>
                {conferindo ? (
                  <button className="btn btn-ghost" onClick={pararConferencia}>Parar conferência</button>
                ) : (
                  <button
                    className="btn btn-primary"
                    disabled={!dados || dados.pendentesConferencia === 0}
                    onClick={conferirNaReceita}
                    title="Consulta a Receita para todas as empresas desta lista que ainda não foram conferidas. Roda no servidor e espera a Receita liberar quando ela pede."
                  >
                    Conferir na Receita
                  </button>
                )}
              </div>
            </div>

            {levando && (
              <div className="carteira-aviso">
                {levando.fase === "fim" ? "Pronto. " : levando.fase === "levando" ? "Levando para a carteira… " : "Localizando os endereços no mapa… "}
                <b>{n(levando.criados)}</b> {levando.criados === 1 ? "virou cliente novo" : "viraram clientes novos"}
                {levando.fase !== "levando" && <>, <b>{n(levando.localizados)}</b> no mapa</>}
                {levando.semLocal > 0 && <>, <b>{n(levando.semLocal)}</b> sem localização (marque o pino no mapa depois)</>}.
                {levando.fase === "localizando" && " Não feche esta página."}
                {levando.mensagem && <div style={{ marginTop: 4 }}>{levando.mensagem}</div>}
              </div>
            )}

            {conferencia && (conferencia.rodando || conferencia.iniciadoEm) && (
              <div className="carteira-aviso">
                {conferencia.rodando
                  ? (conferencia.faltamSegundos > 0
                    ? `A Receita pediu para esperar — retoma em ${conferencia.faltamSegundos}s. `
                    : "Conferindo na Receita… ")
                  : `${conferencia.mensagem || "Conferência terminada."} `}
                <b>{n(conferencia.ativas)}</b> ativas, <b>{n(conferencia.naoAtivas)}</b> fechadas
                {conferencia.falhas > 0 && `, ${n(conferencia.falhas)} sem resposta (ficam para a próxima)`}
                {" · "}faltam {n(conferencia.restam)}.
                {conferencia.rodando && " Pode fechar esta página: o servidor continua sozinho e o que já foi conferido fica gravado."}
              </div>
            )}

            <div className="carteira-tabela-wrap">
              <table className="carteira-tabela">
                <thead>
                  <tr>
                    <th style={{ width: 34 }}>
                      <input
                        type="checkbox"
                        aria-label="Selecionar todas desta página"
                        checked={itens.length > 0 && itens.every((p) => selecionados.has(p.id))}
                        onChange={alternarPagina}
                      />
                    </th>
                    {COLUNAS.map((c) => (
                      <th
                        key={c.campo}
                        className={"ordenavel" + (c.num ? " num" : "")}
                        onClick={() => ordenarPor(c)}
                        title={c.ajuda || "Clique para ordenar"}
                      >
                        {c.rotulo} {filtros.ordenar === c.campo ? (filtros.direcao === "asc" ? "▲" : "▼") : ""}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {itens.length === 0 && !carregando ? (
                    <tr><td colSpan={COLUNAS.length + 1} className="muted" style={{ padding: 20, textAlign: "center" }}>
                      Nenhuma empresa com esses filtros.
                    </td></tr>
                  ) : itens.map((p) => (
                    <tr key={p.id} className={selecionados.has(p.id) ? "marcada" : ""}>
                      <td>
                        <input type="checkbox" checked={selecionados.has(p.id)} onChange={() => alternarSelecao(p)} />
                      </td>
                      <td>
                        <div className="carteira-nome">{p.razaoSocial}</div>
                        <div className="faint" style={{ fontSize: 12 }}>{cnpjFmt(p.cnpj)}</div>
                      </td>
                      <td className="num" title={p.potencialDetalhe}>
                        <span className="chip chip-potencial">★ {p.notaPotencial}</span>
                      </td>
                      <td>{p.ramo || "—"}</td>
                      <td>{p.porte || "—"}</td>
                      <td className="num">{p.capitalSocial != null ? brl(p.capitalSocial) : "—"}</td>
                      <td>{p.bairro || "—"}{!cidade && p.cidade ? <div className="faint" style={{ fontSize: 12 }}>{p.cidade}</div> : null}</td>
                      <td>{p.telefone ? telefoneFmt(p.telefone) : "—"}</td>
                      <td><SituacaoReceita valor={p.situacaoReceita} /></td>
                      <td style={{ fontSize: 12 }}>{p.socios || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {paginas > 1 && (
              <div className="carteira-paginacao">
                <button className="btn btn-ghost" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                  ← Anterior
                </button>
                <span className="muted" style={{ fontSize: 13 }}>Página {pagina} de {paginas}</span>
                <button className="btn btn-ghost" disabled={pagina >= paginas} onClick={() => setPagina((p) => p + 1)}>
                  Próxima →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
