import { useRef, useState } from "react";
import { enviarArquivo } from "../lib/upload";

function Numero({ rotulo, valor, destaque, ajuda }) {
  return (
    <div className={"previa-item" + (destaque ? " destaque" : "")}>
      <span>{rotulo}</span>
      <b>{valor}</b>
      {ajuda && <small className="faint">{ajuda}</small>}
    </div>
  );
}

const n = (v) => (v ?? 0).toLocaleString("pt-BR");

// Importação da lista de prospectos: envia, LÊ A PRÉVIA e só então confirma —
// mesmo fluxo da importação da carteira. A prévia roda tudo no servidor e
// desfaz, então o que ela mostra é o que vai acontecer.
export default function ProspeccaoImportar({ aoConcluir }) {
  const [arquivo, setArquivo] = useState(null);
  const [previa, setPrevia] = useState(null);
  const [concluido, setConcluido] = useState(null);
  const [progresso, setProgresso] = useState(0);
  const [ocupado, setOcupado] = useState("");
  const [erro, setErro] = useState("");
  const [falhouAoGravar, setFalhouAoGravar] = useState(false);
  const entradaRef = useRef(null);

  async function analisar() {
    if (!arquivo) return;
    setOcupado("previa");
    setErro("");
    setPrevia(null);
    setConcluido(null);
    setFalhouAoGravar(false);
    setProgresso(0);
    try {
      const r = await enviarArquivo("/api/prospectos/importar", arquivo, setProgresso);
      setPrevia(r.resumo);
    } catch (e) {
      setErro(e.message);
    } finally {
      setOcupado("");
    }
  }

  async function confirmar() {
    setOcupado("gravar");
    setErro("");
    setFalhouAoGravar(false);
    setProgresso(0);
    try {
      const r = await enviarArquivo("/api/prospectos/importar?confirmar=true", arquivo, setProgresso);
      setConcluido(r.resumo);
      setPrevia(null);
      setArquivo(null);
      if (entradaRef.current) entradaRef.current.value = "";
      aoConcluir?.();
    } catch (e) {
      setErro(e.message);
      setFalhouAoGravar(true);
    } finally {
      setOcupado("");
    }
  }

  const resumo = previa || concluido;

  return (
    <div className="importar">
      <p className="muted" style={{ fontSize: 13 }}>
        Envie a planilha de empresas (.xlsx ou .csv) com uma empresa por linha e cabeçalho na primeira linha.
        Precisa ter pelo menos <b>cnpj</b> e <b>razao_social</b>; o resto (capital, porte, CNAE, endereço,
        telefone, e-mail, município) é aproveitado quando existir. Quem já é cliente é reconhecido pelo CNPJ e
        fica de fora da lista de visita. Importar de novo o mesmo CNPJ atualiza os dados da lista e
        <b> não apaga</b> o que vocês decidiram sobre a empresa.
      </p>

      <div className="importar-envio">
        <input
          ref={entradaRef}
          type="file"
          accept=".xlsx,.csv"
          onChange={(e) => { setArquivo(e.target.files?.[0] || null); setPrevia(null); setConcluido(null); }}
        />
        <button className="btn btn-primary" disabled={!arquivo || Boolean(ocupado)} onClick={analisar}>
          {ocupado === "previa" ? "Analisando…" : "Ver o que vai entrar"}
        </button>
      </div>

      {ocupado && progresso > 0 && progresso < 100 && (
        <div className="importar-progresso"><div style={{ width: `${progresso}%` }} /></div>
      )}
      {ocupado === "gravar" && progresso >= 100 && (
        <p className="muted" style={{ fontSize: 13 }}>
          Gravando… uma lista grande pode levar alguns minutos — <b>não feche esta página</b>.
        </p>
      )}

      {erro && <div className="login-erro">{erro}</div>}

      {resumo && (
        <div className={"importar-previa" + (concluido ? " concluida" : "")}>
          <h4>{concluido ? "Importação concluída" : falhouAoGravar ? "Não chegou a gravar" : "O que vai entrar"}</h4>
          {falhouAoGravar && (
            <p className="muted" style={{ fontSize: 13, marginTop: -6 }}>
              Os números abaixo são o que a análise encontrou e continuam valendo — é só tentar gravar de novo.
            </p>
          )}

          <div className="previa-grade">
            <Numero rotulo="Empresas no arquivo" valor={n(resumo.linhasNoArquivo)} />
            <Numero rotulo="Novas" valor={n(resumo.novos)} destaque />
            <Numero rotulo="Já conhecidas (atualizadas)" valor={n(resumo.atualizados)} />
            <Numero rotulo="Já são clientes" valor={n(resumo.jaClientes)} ajuda="ficam fora da lista de visita" />
            <Numero rotulo="Empresas" valor={n(resumo.empresas)} destaque />
            <Numero
              rotulo="MEI / autônomos" valor={n(resumo.meiAutonomos)}
              ajuda="pelo nome — o dono costuma fazer o serviço"
            />
            {resumo.invalidas > 0 && (
              <Numero rotulo="Linhas ignoradas" valor={n(resumo.invalidas)} ajuda="sem CNPJ válido ou sem nome" />
            )}
            {resumo.repetidas > 0 && (
              <Numero rotulo="CNPJ repetidos" valor={n(resumo.repetidas)} ajuda="vale a última linha" />
            )}
          </div>

          {resumo.cidades?.length > 0 && (
            <div className="previa-lista">
              <span className="filtro-titulo">Cidades no arquivo</span>
              <ul>{resumo.cidades.map((c) => <li key={c.cidade}>{c.cidade}: <b>{n(c.total)}</b></li>)}</ul>
            </div>
          )}

          {resumo.situacaoNoArquivo && (
            <p className="muted" style={{ fontSize: 12 }}>
              Situação que vem escrita no arquivo:{" "}
              {Object.entries(resumo.situacaoNoArquivo).map(([k, v]) => `${k} (${n(v)})`).join(", ")}.
              É uma foto do dia em que a lista foi gerada — não garante que a empresa ainda existe.
            </p>
          )}

          {previa && (
            <div className="importar-confirmar">
              <button className="btn btn-primary" disabled={Boolean(ocupado)} onClick={confirmar}>
                {ocupado === "gravar" ? "Gravando…" : falhouAoGravar ? "Tentar gravar de novo" : "Confirmar e gravar"}
              </button>
              <button className="btn btn-ghost" disabled={Boolean(ocupado)} onClick={() => setPrevia(null)}>
                Cancelar
              </button>
              <span className="faint" style={{ fontSize: 12 }}>Nada foi gravado ainda.</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
