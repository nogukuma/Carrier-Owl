import chromedriver_binary   # これは必ず入れる
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os
import time
import yaml
import datetime
import argparse
import textwrap
from bs4 import BeautifulSoup
import slackweb
import warnings
import urllib.parse
from dataclasses import dataclass
import arxiv
import requests
# setting
warnings.filterwarnings('ignore')


@dataclass
class Result:
    url: str
    title: str
    abstract: str
    words: list
    score: float = 0.0


def calc_score(abst: str, keywords: dict) -> (float, list):
    sum_score = 0.0
    hit_kwd_list = []

    for word in keywords.keys():
        score = keywords[word]
        if word.lower() in abst.lower():
            sum_score += score
            hit_kwd_list.append(word)
    return sum_score, hit_kwd_list


def search_keyword(articles: list, keywords: dict) -> list:
    results = []

    for article in articles:
        url = article['arxiv_url']
        title = article['title']
        abstract = article['summary']
        score, hit_keywords = calc_score(abstract, keywords)
        if score != 0:
            title_trans = get_translated_text('ja', 'en', title)
            abstract = abstract.replace('\n', '')
            abstract_trans = get_translated_text('ja', 'en', abstract)
            abstract_trans = textwrap.wrap(abstract_trans, 40)  # 40行で改行
            abstract_trans = '\n'.join(abstract_trans)
            result = Result(
                    url=url, title=title_trans, abstract=abstract_trans,
                    score=score, words=hit_keywords)
            results.append(result)
    return results


def send2slack(results: list, slack: slackweb.Slack) -> None:

    # 通知
    star = '*'*120
    today = datetime.date.today()
    text = f'{star}\n \t \t {today}\n{star}'
    slack.notify(text=text)
    # descending
    for result in sorted(results, reverse=True, key=lambda x: x.score):
        url = result.url
        title = result.title
        abstract = result.abstract
        word = result.words
        score = result.score

        text_slack = f'''
        \n score: `{score}`
        \n hit keywords: `{word}`
        \n url: {url}
        \n title:    {title}
        \n abstract:
        \n \t {abstract}
        \n {star}
        '''
        slack.notify(text=text_slack)


def send2line(results, line_notify_token):
    line_notify_api = 'https://notify-api.line.me/api/notify'
    headers = {'Authorization': f'Bearer {line_notify_token}'}

    # 通知
    star = '*'*120
    today = datetime.date.today()
    text = f'{star}\n \t \t {today}\n{star}'
    data = {'message': f'message: {text}'}
    requests.post(line_notify_api, headers=headers, data=data)
    # descending
    for result in sorted(results, reverse=True, key=lambda x: x.score):
        url = result.url
        title = result.title
        abstract = result.abstract
        word = result.words
        score = result.score

        text_line = f'''
        \n score: `{score}`
        \n hit keywords: `{word}`
        \n url: {url}
        \n title:    {title}
        \n abstract:
        \n \t {abstract}
        \n {star}
        '''

        data = {'message': f'message: {text_line}'}
        requests.post(line_notify_api, headers=headers, data=data)


def get_translated_text(from_lang: str, to_lang: str, from_text: str) -> str:
    '''
    https://qiita.com/fujino-fpu/items/e94d4ff9e7a5784b2987
    '''

    sleep_time = 1

    # urlencode
    from_text = urllib.parse.quote(from_text)

    # url作成
    url = 'https://www.deepl.com/translator#' \
        + from_lang + '/' + to_lang + '/' + from_text

    # ヘッドレスモードでブラウザを起動
    options = Options()
    options.add_argument('--headless')

    # ブラウザーを起動
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    driver.implicitly_wait(10)  # 見つからないときは、10秒まで待つ

    for i in range(30):
        # 指定時間待つ
        time.sleep(sleep_time)
        html = driver.page_source
        to_text = get_text_from_page_source(html)

        if to_text:
            break

    # ブラウザ停止
    driver.quit()
    return to_text


def get_text_from_page_source(html: str) -> str:
    soup = BeautifulSoup(html, features='lxml')
    target_elem = soup.find(class_="lmt__translations_as_text__text_btn")
    text = target_elem.text
    return text


def get_config() -> dict:
    file_abs_path = os.path.abspath(__file__)
    file_dir = os.path.dirname(file_abs_path)
    config_path = f'{file_dir}/../config.yaml'
    with open(config_path, 'r') as yml:
        config = yaml.load(yml)
    return config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--slack_id', default=None)
    parser.add_argument('--line_token', default=None)
    args = parser.parse_args()
    config = get_config()
    subject = config['subject']
    keywords = config['keywords']

    yesterday = datetime.datetime.today() - datetime.timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y%m%d')
    # datetime format YYYYMMDDHHMMSS
    arxiv_query = f'{subject} AND ' \
                  f'submittedDate:' \
                  f'[{yesterday_str}000000 TO {yesterday_str}235959]'
    articles = arxiv.query(query=arxiv_query,
                           max_results=1000,
                           sort_by='submittedDate',
                           iterative=False)
    results = search_keyword(articles, keywords)

    # slack
    slack_id = os.getenv("SLACK_ID") or args.slack_id
    if slack_id is not None:
        slack = slackweb.Slack(url=slack_id)
        send2slack(results, slack)

    # line
    line_notify_token = os.getenv("LINE_TOKEN") or args.line_token
    if line_notify_token is not None:
        send2line(results, line_notify_token)


if __name__ == "__main__":
    main()
