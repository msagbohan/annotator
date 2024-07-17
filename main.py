import streamlit as st
from streamlit_option_menu import option_menu
import pyrebase

import annotator

# APP PAGE SETTINGS

st.set_page_config(page_title="BAMSCAPE", page_icon=":bird:", layout='wide', initial_sidebar_state='auto')

st.markdown("""
     <style>
       .css-o18uir.e16nr0p33 {
         margin-top: -75px;
       }
     </style>
   """, unsafe_allow_html=True)

st.markdown(
    """
      <style>
          div.stButton > button {background-color: #64B5F6;}
          div.Controls_container__LTeAA > button {background: purple !important;}
          .block-container {
                  padding-top: 2.5rem;
                  padding-bottom: 0rem;
                  padding-left: 5rem;
                  padding-right: 5rem;
              }

          iframe[title="streamlit_text_label.label_select"] .ant-btn {background: orange !important;}
          iframe[title="streamlit_text_label.label_select"] .ant-btn-primary {background: orange !important;}
          .ant-btn {background: violet !important;}
          .ant-btn-primary {background: violet !important;}
          button.ant-btn {background: violet !important;}
          button.ant-btn-primary {background: violet !important;}
      </style>
    """, unsafe_allow_html=True
)

# MAIN PAGE HEADER

col1, col2 = st.columns((1, 10))
with col1:
    st.image('bioacoustics_logo_large2.gif', width=90)
with col2:
    st.header(':green[Brazilian Team] &mdash;' ' ' ':violet[_Bioacoustics_ :bird:]')

# FIREBASE KEYS AND AUTHENTICATION

firebaseConfig = {
    'apiKey': st.secrets["config_firebase"]['apiKey'],
    'authDomain': st.secrets["config_firebase"]['authDomain'],
    'projectId': st.secrets["config_firebase"]['projectId'],
    'databaseURL': st.secrets["config_firebase"]['databaseURL'],
    'storageBucket': st.secrets["config_firebase"]['storageBucket'],
    'messagingSenderId': st.secrets["config_firebase"]['messagingSenderId'],
    'appId': st.secrets["config_firebase"]['appId'],
    'measurementId': st.secrets["config_firebase"]['measurementId'],
}

fire = pyrebase.initialize_app(firebaseConfig)
auth = fire.auth()

# DATABASE

db = fire.database()
storage = fire.storage()

# MAIN APP

if 'useremail' not in st.session_state:
    st.session_state.useremail = ''


def f():
    try:
        auth.sign_in_with_email_and_password(email, password)
        st.session_state.signout = True
        st.session_state.signedout = True
        st.session_state.useremail = email
    except:
        st.text(' ')


def t():
    st.session_state.signout = False
    st.session_state.signedout = False


if 'signedout' not in st.session_state:
    st.session_state['signedout'] = False

if 'signout' not in st.session_state:
    st.session_state['signout'] = False

if not st.session_state['signedout']:
    st.subheader(':orange[Please, log-in to access the interface]')
    email = st.text_input(':blue[E-mail]', placeholder='Enter your e-mail')
    password = st.text_input(':blue[Password]', placeholder='Enter your password', type='password')

    if st.button('Login', on_click=f):
        try:
            auth.sign_in_with_email_and_password(email, password)
            st.session_state.useremail = email
            st.session_state.signout = True
            st.session_state.signedout = True

        except:
            st.warning('Login failed, please enter a valid email/password')

if st.session_state.signout:
    username = st.session_state.useremail
    username = username.split('@')[0]
    st.subheader(f':blue[Hello]' + ' ' + f':gray[{username}]' + ' ' + '👋🏻')
    st.button('Sign out', on_click=t)
    st.markdown('#####')
    bio = option_menu(menu_title=None,
                      options=['Home', 'Database', 'Data analysis', 'Identification'],
                      icons=['house', 'volume-up', 'soundwave', 'layers'],
                      default_index=0,
                      styles={"nav-link": {"font-size": "17px", "text-align": "left", "margin": "0px"},
                              "nav-link-selected": {"background-color": "orange"}},
                      orientation='horizontal')

    if bio == 'Identification':
        annotator.iden()

    st.markdown('#')

