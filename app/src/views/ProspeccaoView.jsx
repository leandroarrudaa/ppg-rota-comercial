import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { brl, telefoneFmt } from "../lib/format";

const ProspeccaoImportar = lazy(() => import("./ProspeccaoImportar"));

const TAMANHO_PAGINA = 50;
const CIDADE_PADRAO = "PONTA GROSSA";

// ascPadrao: texto começa em A-Z; número começa do maior — é o que se quer ver
// primeiro. Mesma regra das outras tabelas do app.
const COLUNAS = [
  { campo: "razaoSocial", rotulo: "Empresa", ascPadrao: true },
  { campo: "ramo", rotulo: "Ramo", ascPadrao: true },
  { campo: "porte", rotulo: "Porte", ascPadrao: true },
  { campo: "capitalSocial", rotulo: "Capital social", ascPadrao: false, num: true },
  { campo: "bairro", rotulo: "Bairro", ascPadrao: true },
  { campo: "telefone", rotulo: "Telefone", ascPadrao: true },
  { campo: "situacaoLista", rotulo: "Situação no arquivo", ascPadrao: true,
    ajuda: "Vem escrita na lista, que é uma foto antiga. Ainda não foi conferida na Receita." },
];

const COLUNAS_RAMOS = [
  { campo: "ramo", rotulo: "Ramo", ascPadrao: true },
  { campo: "empresas", rotulo: "Empresas", num: true },
  { campo: "micro", rotulo: "Micro", num: true },
  { campo: "pequena", rotulo: "Pequena", num: true },
  { campo: "demais", rotulo: "Média/grande", num: true, ajuda: "Porte \"Demais\" na Receita: fora do Simples" },
  { campo: "total", rotulo: "Total com MEI", num: true },
];

const FILTROS_INICIAIS = { busca: "", ramo: "", tipo: "empresa", porte: "", ordenar: "capitalSocial", direcao: "desc" };

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
  }, [carregar]);

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

  // o painel fica aberto de propósito: é nele que aparece o "Importação concluída"
  function aoImportar() {
    setPagina(1);
    carregarResumo();
  }

  return (
    <div className="gestao">
      <div className="gestao-cabecalho">
        <h3 style={{ margin: 0 }}>Prospecção</h3>
        <p className="muted" style={{ fontSize: 13 }}>
          Empresas que ainda não são clientes, vindas da lista importada. A situação que aparece vem do
          próprio arquivo (uma foto antiga): <b>ainda não foi conferida na Receita</b>, então parte dessas
          empresas pode já ter fechado.
        </p>
      </div>

      <div className="gestao-corpo">
        {erro && <div className="login-erro">{erro}</div>}

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
              </span>
            </div>

            <div className="carteira-tabela-wrap">
              <table className="carteira-tabela">
                <thead>
                  <tr>
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
                    <tr><td colSpan={COLUNAS.length} className="muted" style={{ padding: 20, textAlign: "center" }}>
                      Nenhuma empresa com esses filtros.
                    </td></tr>
                  ) : itens.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <div className="carteira-nome">{p.razaoSocial}</div>
                        <div className="faint" style={{ fontSize: 12 }}>{cnpjFmt(p.cnpj)}</div>
                      </td>
                      <td>{p.ramo || "—"}</td>
                      <td>{p.porte || "—"}</td>
                      <td className="num">{p.capitalSocial != null ? brl(p.capitalSocial) : "—"}</td>
                      <td>{p.bairro || "—"}{!cidade && p.cidade ? <div className="faint" style={{ fontSize: 12 }}>{p.cidade}</div> : null}</td>
                      <td>{p.telefone ? telefoneFmt(p.telefone) : "—"}</td>
                      <td>{p.situacaoLista || "—"}</td>
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
