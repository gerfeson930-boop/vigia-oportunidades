# Vigia de Oportunidades (revenda: OLX em MG, Enjoei Brasil todo e promoções do Pelando)

Fica checando o **OLX de Minas Gerais** e o **Enjoei** (que envia para o Brasil todo), com 3 buscas ao
mesmo tempo, e repete 10 minutos depois de cada rodada. Quando aparece um anúncio abaixo da média de
anúncios parecidos, ele te avisa no Telegram com foto, preço e link.

## Instalar

1. No Telegram, fale com **@BotFather**, mande `/newbot` e guarde o token.
2. Dê dois cliques em **`instalar.bat`**. Ele instala tudo, pede o token (que não aparece na tela) e
   pergunta se o vigia deve iniciar junto com o Windows.
3. Abra o seu bot no Telegram e mande **`/start`**. O primeiro chat a fazer isso vira o dono e é o
   único que o bot atende.
4. Mande **`/pacote`** para cadastrar as buscas de revenda sugeridas, ou crie as suas com `/nova`.

## Comandos no Telegram

| Comando | O que faz |
|---|---|
| `/nova iphone 13 -pro -max ate 2300 desc 30` | cria uma busca (`-palavra` exclui, `ate` = teto, `desc` = % abaixo da média) |
| `/nova lote eletronicos todos` | avisa **todo** anúncio novo (para lotes e queima de estoque) |
| `/lista` · `/remove 3` · `/desliga 3` · `/liga 3` | gerenciar as buscas |
| `/faixas` | mostra as faixas de desconto |
| `/forte 35` · `/desconto 25` · `/leve 12` | % para 🔥 pechincha, ✅ boa oferta e 💡 resumo (`/leve 0` desliga) |
| `/desconto 3 40` | % de boa oferta só para a busca #3 |
| `/agora` · `/pausa` · `/retoma` · `/status` | controle do vigia |

## Compartilhar com um amigo

Mande o link do seu bot (`t.me/<usuario_do_bot>`) ou encaminhe o contato dele. Quando o amigo mandar
`/start`, chega para você um pedido com **/liberar_…** e **/recusar_…** (é só tocar). Liberado, ele recebe
os mesmos alertas que você e pode ver achados, buscas e status e adicionar produtos; apagar buscas,
mudar faixas e pausar continua só com você. Veja e tire pessoas em `/pessoas`. Os alertas dele também
dependem do seu PC estar ligado.

## Como ele decide

- **1ª rodada de cada busca (e de cada plataforma nova):** só aprende os preços, sem alertas.
- **Depois disso**, para cada anúncio novo, compara com a **mediana** (da própria plataforma, quando
  ela tem anúncios suficientes):
  - 🔥 **35%+ abaixo:** pechincha, com foto, na hora e sempre primeiro
  - ✅ **25%+:** boa oferta, com foto
  - 💡 **12%+:** entra num resumo no fim da rodada, do maior para o menor desconto
- Também avisa quando um anúncio já conhecido baixa de preço.
- **Promoções do Pelando** (produto novo em loja, postadas nas últimas 48 h) são comparadas com a
  média dos **usados**: 🔥 se o novo sai bem abaixo dela, ✅ se sai mais barato que ela, 💡 no resumo
  se for só uma promoção. Elas não entram na média dos usados.
- Ignora máquina inteira em busca de peça ("pc gamer rtx 3060" na busca "rtx 3060"), fone avulso
  ("lado L") e termos típicos de réplica.
- Se uma plataforma bloquear, fica 1 hora sem acessá-la e volta a fazer 1 busca por vez nesse tempo.
- Precisa de **15 anúncios de referência** antes de confiar na média. Buscas muito específicas, com
  poucos anúncios em MG, só avisam pelo teto (`ate`).
- Anúncio com "urgente", "mudança", "aceito proposta" etc. precisa de 10 pontos a menos de desconto.
- Anúncio "com defeito" / "para peças" fica fora da média e só vira alerta se estiver 50% abaixo.
- Abaixo de 35% da média, o anúncio é ignorado: quase sempre é jogo, controle, capa ou golpe.
  Entre 35% e 50% da média, o alerta vem com ⚠️.
- Busca genérica mistura modelos ("thinkpad" junta T410 de R$ 189 com P16 de R$ 13 mil). Prefira
  modelos específicos ou use `-palavra`.

## Mercado Livre (opcional)

O site do ML exige login para acesso automatizado, então o vigia usa só a **API oficial**. Para ligar,
crie um app em developers.mercadolivre.com.br e rode `configurar_ml.bat`. Se a API recusar a busca, o
vigia avisa e segue só com o OLX.

## Arquivos

- `iniciar.bat`: roda com uma janela aberta, para ver o que está acontecendo
- `parar.bat`: encerra o vigia
- `dados/`: configuração, banco de anúncios e log (`vigia.log`). O token fica só aqui no seu PC.

Se o OLX bloquear (captcha ou erro 403), o vigia **não tenta driblar**: fica 1 hora sem acessar o site
e te avisa.
