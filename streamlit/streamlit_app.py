# Code refactored from https://docs.streamlit.io/knowledge-base/tutorials/build-conversational-apps
# pip install -r requirements.txt
# <div class="primary-image svelte-wgcq7z"> image source

import streamlit as st
from openai import OpenAI

from operator import itemgetter
from langchain_community.vectorstores import faiss
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

import numpy as np
import base64
from PIL import Image
from io import BytesIO
from gensim.models import Word2Vec
from input_image import read_image
from combined import Recommender
import json
import pickle
import dill
import config
import os
from chat import CustomDataChatbot
import ast
import re

# st.write(os.getcwd())
# load in data and models
@st.cache_resource
def load_data():
    model = Word2Vec.load(config.W2V_PATH)
    # load in tfdif model and encodings
    with open(config.PICKLE_FULL_PATH, 'rb') as f:
        full_recipes = pickle.load(f)
    with open(config.TFIDF_MODEL_PATH, 'rb') as f:
        tfidf = dill.load(f)
    with open(config.TFIDF_ENCODING_PATH, 'rb') as f:
        tfidf_encodings = dill.load(f)

    rec = Recommender(model, tfidf, tfidf_encodings, full_recipes)
    return model, full_recipes, tfidf, tfidf_encodings, rec

model, full_recipes, tfidf, tfidf_encodings, rec = load_data()

diets = [None, 'vegan', 'lactose free']
cuisines = [None, 'african', 'american', 'asian', 'creole and cajun', 
            'english','french','greek','indian','italian',
            'latin american','mediterranean','middle eastern',
            'spanish', 'thai']
types = [None, 'breakfast and brunch', 'main dish', 'side dish', 'salad', 'baked goods']
condiments = ['salt', 'pepper', 'oil']


# create page header
st.header(':cook: PicToPlate', divider='rainbow')
st.subheader("Welcome to PicToPlate! Cooking at home has never been easier.")

st.markdown('PicToPlate is an innovation application that allows home chefs to input an image of ingredients \
            they have, and PicToPlate will return a list of recipes they can cook using what they already have. \
            To get started, follow the instructions below.')

#create page caption
st.caption(":shallow_pan_of_food: A cooking assistant powered by OpenAI LLM")

#default on screen message
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "Please upload an image so we can get started!"}]

#website sidebar, with api_key input and filters/sort
with st.sidebar:
    st.session_state['api_key'] = st.text_input("OpenAI API Key", key="chatbot_api_key", type="password")
    "[Get an OpenAI API key](https://platform.openai.com/account/api-keys)"
    if st.button('Use Provided API Key'):
        st.session_state['api_key'] = st.secrets.db_credentials.openai_key
    

    


############# Set up chatbot ################

def retrieve_names(dishes):
    dishes_list = dishes.split('\n')
    cleaned_dishes = []

    # Process each line to extract and clean the dish names
    for line in dishes_list:
        # Split the line on the period to remove the initial numbering
        parts = line.split('.', 1)
        if len(parts) > 1:
            # Extract the part after the period
            dish = parts[1].strip()
            # Convert to lower case
            dish = dish.lower()
            # Remove all non-alphanumeric characters (excluding spaces)
            dish = re.sub('[^0-9a-zA-Z ]+', '', dish)
            # Add the cleaned name to the list
            cleaned_dishes.append(dish.replace(' ', ''))
    return cleaned_dishes

def retrieve_info(message, recs):
    names = retrieve_names(message)
    out_df = recs[recs['name_pack'].isin(names)]
    return out_df[['name', 'link', 'ingredients_x']]

def categorical_prompt(diet, cuisine, type):
    # f"Please find 3 recipes that fulfills the requirements:{categorical} from the 30 recipes,
    #   also considering the ingredients available."
    diet_p = ''
    cuisine_p = ''
    type_p = ''

    if diet is not None:
        diet_p = f'with {diet} dietary restriction'
    if cuisine is not None:
        cuisine_p = f'in {cuisine} cuisine'
    if type is not None:
        type_p = f'that are {type}'
    
    prompt = f'Fine 3 recipes from the original dataset {type_p} {diet_p} {cuisine_p}. Consider the ingredients available. Return only the recipe names.'
    return prompt


# if 'results' not in st.session_state:
#     st.session_state['results'] = None


################## Enhance Display and Interaction ###################
def display_info(df):
    message = ""
    for count, (index, row) in enumerate(df.iterrows()):
        link = 'https://' + row['link']
        # Format current message, assuming out1 contains titles or descriptions
        # and appending the link and ingredients from the DataFrame
        cur_message = f"**{count+1}. {row['name']}** [Recipe Link]({link})\n\n" \
                      f"**Ingredients:** {row['ingredients_x']}\n\n---\n\n"
        # Append the current message to the overall message
        message += cur_message
    return message

# def display_recipes(recipes_df):
#     """Display recipe names as clickable links with ingredients."""
#     for index, row in recipes_df.iterrows():
#         # Recipe name as clickable link
#         st.markdown(f"[{row['name']}]({row['link']})")
#         # Display ingredients related to the recipe
#         st.markdown(f"Ingredients: {row['ingredients_x']}")
#         st.markdown("---")  # Separator

################## SideBar and Inputs ###################################

with st.sidebar:
    st.subheader("Filters")
    with st.form('category_form', clear_on_submit=True):
        st.selectbox('Select Dietary Restriction', diets, key='diet')
        st.selectbox('Select Cuisines', cuisines,key='cuisine')
        st.selectbox('Select Meal Type', types, key='type')

        "---"
        submitted = st.form_submit_button('Save inputs')

 


######################### Use input_image/image_reader instead ##########
openai_api_key = st.secrets.db_credentials.openai_key
# openai_api_key = st.session_state['api_key']
uploaded_file = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"])

def image_to_base64(image: Image.Image) -> str:
    buffered = BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode()

if uploaded_file is not None:
    # Display the uploaded image
    image = Image.open(uploaded_file)

    # Convert the image to base64
    image_base64 = image_to_base64(image)

    # Display image 
    left, mid, right = st.columns([1,2,1])
    with mid:
        st.image(image, width= 300, caption='Uploaded Image.')

    if uploaded_file and not openai_api_key:
        st.info("Please add your OpenAI API key to continue.")
    
     # User clicks the button to start processing
    if st.button('Identify Ingredients') and openai_api_key:

        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json"
        }
        with st.spinner('Identifying ingredients..'):
            response = read_image.ingredient_identifier(image_base64, 'streamlit', openai_api_key)
        ing = json.loads(response['choices'][0]['message']['content'].strip('` \n').strip('json\n'))['items']
        ing_message = 'Looks like we have ' + ', '.join(ing) + ' available.'
        st.session_state['ingredients'] = ing
        st.chat_message("assistant").write(ing_message)

        # st.session_state["messages"] = [{"role": "assistant", "content": ing_message}]
        with st.spinner('Pulling recipes.. It would take about 1 min'):
            initial_recs = rec.get_recommend(ing, 30)
            initial_recs['name_pack'] = initial_recs['name'].str.replace(' ','')
            st.session_state['recommends'] = initial_recs

        CDchatbot = CustomDataChatbot()
        chatbot = CDchatbot.query_llm(initial_recs, openai_api_key)
        question= f"what are at least 4 recipes that can be made using the available ingredsents: {ing}? Return only the recipe names."
        result = chatbot.invoke({"question": question,
                        'chat_history': []})
        
        # st.write(result['answer'].content)
        top_df = retrieve_info(result['answer'].content, initial_recs)
        message = display_info(top_df)
        # st.write(message)
        
        st.chat_message('assistant').write(message)
        st.session_state.messages.append({"role": "assistant", "content": message})
        st.session_state['agent'] = chatbot

## Side bar
if submitted:
    if 'agent' in st.session_state:
        categorical = 'Diet: ' + str(st.session_state['diet']) + '; Cuisine: '+ str(st.session_state['cuisine']) +'; Meal type: ' + str(st.session_state['type'])
        st.write(f'Current choices: {categorical}')

        initial_recs = st.session_state['recommends']
        chatbot = st.session_state['agent']
        prompt = categorical_prompt(st.session_state['diet'], st.session_state['cuisine'], st.session_state['type'])
        response = chatbot.invoke({"question": prompt})

        new_df = retrieve_info(response['answer'].content, initial_recs)
        new_message = display_info(new_df)
        st.chat_message('assistant').write(new_message)
        st.session_state.messages.append({"role": "assistant", "content": new_message})

        # pulled_recipe = response['answer']
        # st.chat_message('assistant').write(pulled_recipe.content)
        # st.session_state.messages.append({"role": "assistant", "content": pulled_recipe.content})

prompt = st.chat_input("Further questions")
if prompt and 'agent' in st.session_state:
    chatbot = st.session_state['agent']
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    with st.chat_message('assistant'):

        response = chatbot.invoke({"question": prompt})
        st.write(response['answer'].content)
        st.session_state.messages.append({"role": "assistant", "content": response['answer'].content})

    
