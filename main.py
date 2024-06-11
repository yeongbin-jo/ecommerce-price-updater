import json
import traceback
from typing import Tuple

import httpx
import parsel
import pandas as pd
from pylab_sdk import get_latest_agents
from loguru import logger


AGENT = get_latest_agents().get('macOS')
BYPASS_HEADER = {
    'User-Agent': AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.6,nb;q=0.5',
    'Cache-Control': 'max-age=0',
    'Upgrade-Insecure-Requests': '1',
    'Priority': 'u=0,i',
    'Sec-Ch-Ua': '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"macOS"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}


def get_musinsa_price(url: str) -> Tuple[bool, int]:
    # https://www.musinsa.com/app/goods/4112962
    res = httpx.get(url, headers={
        'User-Agent': AGENT
    })
    selector = parsel.Selector(res.text)
    # <meta property="product:price:amount" content="76800"> 태그에서 content 값 가져오기
    price = selector.css('meta[property="product:price:amount"]::attr(content)').extract_first()
    # <span class="product-not-sale"> 태그에서 품절 여부 가져오기
    is_sold_out = selector.css('span.product-not-sale').extract_first() is not None
    return is_sold_out, int(price)


def get_smartstore_price(url: str) -> Tuple[bool, int]:
    res = httpx.get(url, headers=BYPASS_HEADER)
    selector = parsel.Selector(res.text)
    # <script data-react-helmet="true" type="application/ld+json"> 내부 스크립트를 JSON으로 파싱
    react_helmet = selector.css('script[data-react-helmet="true"][type="application/ld+json"]::text').extract_first()
    data = json.loads(react_helmet)
    price = data.get('offers', {}).get('price', 0)
    is_sold_out = data.get('offers', {}).get('availability') == 'https://schema.org/OutOfStock'
    return is_sold_out, price


def get_coupang_price(url: str) -> Tuple[bool, int]:
    res = httpx.get(url, headers=BYPASS_HEADER)
    selector = parsel.Selector(res.text)
    # <span class="total-price"> 태그에서 가격 가져오기
    price = selector.css('span.total-price > strong::text').extract_first()
    price = int(price.replace(',', '').replace('원', ''))
    # <button class="prod-buy-btn" disabled> 태그에서 품절 여부 가져오기
    is_sold_out = selector.css('button.prod-buy-btn[disabled]').extract_first() is not None
    return is_sold_out, price


def get_gmarket_price(url: str) -> Tuple[bool, int]:
    res = httpx.get(url, headers={
        'User-Agent': AGENT
    })
    start_index = res.text.find('var eventObj = {') + len('var eventObj = ')
    end_index = res.text.find('};', start_index) + 1
    data = json.loads(res.text[start_index:end_index])
    price = data.get('price', 0)
    # 구매하기 버튼 활성화 여부로 품절 여부 확인
    selector = parsel.Selector(res.text)
    # button.btn_primary.btn_blue 버튼이 disabled면 품절
    is_sold_out = selector.css('button.btn_primary.btn_blue[disabled]').extract_first() is not None
    return is_sold_out, price


def get_oliveyoung_price(url: str) -> Tuple[bool, int]:
    res = httpx.get(url, headers={
        'User-Agent': AGENT
    })
    selector = parsel.Selector(res.text)
    # <input type="hidden" name="finalPrc" id="finalPrc" value="23900" /> 에서 value 가져오기
    price = selector.css('input#finalPrc::attr(value)').extract_first()
    # <button class="btnSoldout dupItem goods_cart" style="display: none;" onclick="javascript:;">일시품절</button>
    # 버튼의 스타일이 display: none;이 아니면 품절
    is_sold_out = selector.css('button.btnSoldout.dupItem.goods_cart[style="display: none;"]').extract_first() is None
    return is_sold_out, int(price)


def get_price(url: str) -> Tuple[bool, int]:
    if 'musinsa.com' in url:
        return get_musinsa_price(url)
    elif 'smartstore.naver.com' in url:
        return get_smartstore_price(url)
    elif 'coupang.com' in url:
        return get_coupang_price(url)
    elif 'gmarket' in url:
        return get_gmarket_price(url)
    elif 'oliveyoung' in url:
        return get_oliveyoung_price(url)
    else:
        raise ValueError(f'Invalid URL: {url}')


def main():
    filename = 'items.xlsx'
    df = pd.read_excel(filename)
    # 품절 칼럼의 dtype을 bool로 선언
    df['품절'] = False

    # 소싱처 칼럼의 URL들을 읽어서 가격 및 품절 여부를 데이터 프레임에 업데이트 한 뒤 다시 파일에 저장
    for idx, row in df.iterrows():
        try:
            url = row['소싱처']
            is_sold_out, price = get_price(url)
            df.loc[idx, '품절'] = is_sold_out
            df.loc[idx, '변동된가격'] = price
            logger.info(f'{row["상품명"]} - {price}원, 품절: {is_sold_out}')
        except Exception as e:
            traceback.print_exc()
            logger.error(e)

    df.to_excel(filename, index=False)


def test():
    print(get_price('https://smartstore.naver.com/bomnamall/products/10399545901'))
    print(get_price('https://www.musinsa.com/app/goods/763821'))
    print(get_price('https://www.coupang.com/vp/products/7402538023'))
    print(get_price('https://item.gmarket.co.kr/Item?goodscode=3384154261&ver=20240611'))
    print(get_price('https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000205091'))


if __name__ == '__main__':
    main()
