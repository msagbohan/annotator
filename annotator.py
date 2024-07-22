import streamlit as st
import os
import pandas as pd
import numpy as np
import gspread
from google.oauth2 import service_account
import glob
import soundfile as sf
from maad import sound
from maad.util import power2dB
from skimage import transform
import logging
import zipfile
import tempfile
from datetime import datetime
import matplotlib.pyplot as plt

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@st.cache_resource
def authorize_google_sheets():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    return client


def get_google_sheet_data(rec_name):
    client = authorize_google_sheets()
    sheet = client.open("XP_final_annotations").worksheet("rec_name")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return df


def get_annotation_status():
    client = authorize_google_sheets()
    sheet = client.open("XP_annotation_status").worksheet("status")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    # Ensure required columns are present
    if 'cluster_folder' not in df.columns:
        df['cluster_folder'] = ''
    if 'user' not in df.columns:
        df['user'] = ''
    if 'status' not in df.columns:
        df['status'] = ''
    if 'timestamp' not in df.columns:
        df['timestamp'] = ''
    return df


def update_annotation_status(cluster_folder, user, status):
    client = authorize_google_sheets()
    sheet = client.open("XP_annotation_status").worksheet("status")
    df = get_annotation_status()
    idx = df[df['cluster_folder'] == cluster_folder].index
    if not idx.empty:
        sheet.update_cell(idx[0] + 2, 2, user)
        sheet.update_cell(idx[0] + 2, 3, status)
        sheet.update_cell(idx[0] + 2, 4, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    else:
        sheet.append_row([cluster_folder, user, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])


@st.cache_data
def load_audio_files(folder):
    audio_files = glob.glob(os.path.join(folder, "*.WAV"))
    logger.debug(f"Audio files loaded from {folder}: {audio_files}")
    return sorted(audio_files)  # Sort audio files alphabetically


#@st.cache_data
def plot_spec(file_path, cmap: str):
    import matplotlib.pyplot as plt
    s, fs = sound.load(file_path)
    duration = len(s) / fs

    # Adjust figure size based on the duration of the audio file
    if duration < 1:
        fig_size = (2, 2)
    elif duration < 2:
        fig_size = (2.5, 2)
    elif duration < 3:
        fig_size = (4, 2.5)
    else:
        fig_size = (5, 3.5)
    Sxx, tn, fn, ext = sound.spectrogram(s, fs, nperseg=1024, noverlap=512, flims=(0, fs // 2))
    Sxx_db = power2dB(Sxx, db_range=70)
    Sxx_db = transform.rescale(Sxx_db, 0.5, anti_aliasing=True, channel_axis=None)
    fig, ax = plt.subplots(figsize=fig_size)
    img = ax.imshow(Sxx_db, aspect='auto', extent=ext, origin='lower', interpolation='bilinear', cmap=cmap)
    fig.colorbar(img, ax=ax, format="%+2.0f dB")
    ax.set(title='', xlabel='Time [s]', ylabel='Frequency [Hz]')
    plt.tight_layout()
    spectrogram_path = 'temp_spectrogram.png'
    plt.savefig(spectrogram_path)
    plt.close(fig)
    st.image(spectrogram_path)



@st.cache_data
def spacing():
    st.markdown("<br></br>", unsafe_allow_html=True)


def update_google_sheet(client, rec_name, annotations_df):
    sheet = client.open("XP_final_annotations").worksheet(rec_name)
    sheet.clear()  # Clear existing data
    sheet.update([annotations_df.columns.values.tolist()] + annotations_df.values.tolist())


def plot_pie_chart(annotations_df):
    total_clusters = len(annotations_df['cluster_number'].unique())
    annotated_clusters = annotations_df[annotations_df['validated_class'] != 0]['cluster_number'].nunique()
    remaining_clusters = total_clusters - annotated_clusters
    labels = 'Validated Clusters', 'Pending Validations'
    sizes = [annotated_clusters, remaining_clusters]
    colors = ['#1fd655', '#ff9999']
    explode = (0.1, 0)  # explode the 1st slice
    fig1, ax1 = plt.subplots(figsize=(6, 4))
    wedges, texts, autotexts = ax1.pie(sizes, explode=explode, labels=labels, colors=colors, autopct='%1.1f%%',
            shadow=True, startangle=90)
    plt.setp(autotexts, size=13, weight="bold")
    ax1.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
    st.pyplot(fig1)


def iden():
    # Set up the credentials and client
    st.markdown('#####')
    st.header("Bamscape Clusters Annotator")
    client = authorize_google_sheets()

    # Select a recorder to analyze
    rec_name = st.selectbox('**:violet[Please, select a recorder to analyze]**',
                            options=['rec3dmu', 'rec4dmu', 'rec6dmu', 'rec7dmu'])

    if rec_name:
        # Load the CSV files and Google Sheets
        sheet = client.open("XP_final_annotations").worksheet(f"{rec_name}")
        final_annotations = pd.DataFrame(sheet.get_all_records())
        st.session_state.final_annotations = final_annotations
        annotations_df = st.session_state.final_annotations
        csv_file = f'{rec_name}_all_CLUSTERS_COMBINED.csv'

        # Display the pie chart
        plot_pie_chart(annotations_df)

        # Filter out the annotated rows based on specific columns
        unannotated_df = annotations_df[(annotations_df['validated_class'] == 0) |
                                        (annotations_df['validated_specie'] == 0) |
                                        (annotations_df['validator_name'] == 0)]

        # Load the initial state from the Google Sheet
        if 'folders' not in st.session_state:
            folders = unannotated_df['cluster_number'].astype(str).unique()
            st.session_state.folders = {
                folder: unannotated_df[unannotated_df['cluster_number'].astype(str) == folder]['period'].astype(
                    str).unique().tolist() for folder in folders if folder.strip() != ''}

        # Get current annotation status
        annotation_status = get_annotation_status()

        # Check if user has previously uploaded files for the selected rec_name and store in session state
        if 'uploaded_files' not in st.session_state:
            st.session_state.uploaded_files = {}

        # Allow the user to upload multiple ZIP files if not already uploaded
        if rec_name not in st.session_state.uploaded_files:
            uploaded_files = st.file_uploader(f"**:violet[Upload a ZIP file containing Clusters folders of {rec_name}]**", type=["zip"],
                                              accept_multiple_files=True)
            if uploaded_files:
                st.session_state.uploaded_files[rec_name] = uploaded_files

        # Use the extracted directory from session state or uploaded files
        if rec_name in st.session_state.uploaded_files:
            # Create a temporary directory to extract the ZIP files
            with tempfile.TemporaryDirectory() as tmpdir:
                for uploaded_file in st.session_state.uploaded_files[rec_name]:
                    with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
                        zip_ref.extractall(tmpdir)

                st.success(f"Clusters folders extracted successfully")

                # Log the extracted files and directories
                for root, dirs, files in os.walk(tmpdir):
                    logger.debug(f"Extracted root: {root}")
                    logger.debug(f"Extracted dirs: {dirs}")
                    logger.debug(f"Extracted files: {files}")

                # Use the extracted directory as the base path
                base_path = tmpdir

                col1, col2, col3 = st.columns(3)
                selected_folder = None
                selected_subfolder = None
                folder_in_use = None
                with st.container():
                    with col1:
                        if st.session_state.folders:
                            # Check which folders are currently being annotated
                            available_folders = [folder for folder in st.session_state.folders.keys()
                                                 if folder not in
                                                 annotation_status[annotation_status['status'] == 'in use']['cluster_folder'].values]
                            if available_folders:
                                selected_folder = st.selectbox("**:violet[Select a cluster folder to analyze]**",
                                                               available_folders)
                                logger.debug(f"Selected folder: {selected_folder}")
                            else:
                                st.success(
                                    "Congratulations, all the clusters have been annotated! Please select another recorder to annotate.")
                        else:
                            st.success(
                                "Congratulations, all the clusters have been annotated! Please select another recorder to annotate.")
                    with col2:
                        if selected_folder:
                            # Check if the selected folder is currently being annotated
                            in_use_status = annotation_status[(annotation_status['cluster_folder'] == selected_folder) & (annotation_status['status'] == 'in use')]
                            if not in_use_status.empty:
                                folder_in_use = in_use_status.iloc[0]['user']
                                st.error(f"The selected cluster folder is currently being annotated by {folder_in_use}. Please select another folder.")
                                selected_folder = None
                            else:
                                subfolders = st.session_state.folders[selected_folder]
                                if subfolders:
                                    selected_subfolder = st.selectbox("**:violet[Select a subfolder to analyze]**", subfolders)
                                    logger.debug(f"Selected subfolder: {selected_subfolder}")
                    with col3:
                        selected_cmap = st.selectbox("**:violet[Choose a colormap to display spectrograms]**",
                                                     options=['jet', 'Greys', 'plasma', 'viridis', 'inferno'])

                if selected_folder and selected_subfolder:
                    # Mark the folder as in use
                    update_annotation_status(selected_folder, st.session_state.useremail, "in use")

                    subfolder_path = os.path.join(base_path, selected_folder, selected_subfolder)
                    logger.debug(f"Subfolder path: {subfolder_path}")

                    for root, dirs, files in os.walk(subfolder_path, topdown=False):
                        targetfolder = files
                        logger.debug(f"Files in subfolder: {files}")
                        st.write(targetfolder)
                        st.markdown("---")

                    audio_files = load_audio_files(subfolder_path)
                    logger.debug(f"Audio files found: {audio_files}")

                    if audio_files:
                        form = st.form(key=f"user_form")
                        annotations = []  # Initialize annotations list here
                        with form:
                            for i, audio_file in enumerate(audio_files):
                                file_name = os.path.basename(audio_file)
                                cols = [1.70, .8, 1, 1, 1, 1]
                                col1, col2, col3, col4, col5, col6 = st.columns(cols)
                                with col1:
                                    st.markdown(f"<h6 style='text-align: center; color: green;'>ROI: {file_name} </h10>", unsafe_allow_html=True)
                                    with st.spinner('Processing...'):
                                        plot_spec(audio_file, cmap=selected_cmap)
                                with col2:
                                    st.markdown(f"<h2 style='text-align: center; color: black;'></h10>",
                                                unsafe_allow_html=True)
                                    st.markdown('######')
                                    audio_data, audio_sr = sf.read(audio_file)
                                    # Adding a 1-second buffer of silence at the beginning of the audio
                                    silence = np.zeros(int(1 * audio_sr))
                                    audio_data_with_silence = np.concatenate([silence, audio_data])
                                    st.audio(audio_data_with_silence, format='audio/wav', sample_rate=audio_sr)
                                with col3:
                                    st.markdown('#####')
                                    st.markdown(f"<h4 style='text-align: center; color: blue;'>Group</h5>",
                                                unsafe_allow_html=True)
                                    suggested_group = annotations_df.loc[
                                        annotations_df['filename_ts'] == file_name, 'suggested_class'].values[0]
                                    group_input = st.text_input("*(modify the text if needed)*", value=suggested_group,
                                                                key=f"group_{file_name}")
                                with col4:
                                    st.markdown('#####')
                                    st.markdown(f"<h4 style='text-align: center; color: blue;'>Species</h5>",
                                                unsafe_allow_html=True)
                                    suggested_label = annotations_df.loc[
                                        annotations_df['filename_ts'] == file_name, 'suggested_label'].values[0]
                                    scientific_name_input = st.text_input("*(modify the text if needed)*",
                                                                          value=suggested_label,
                                                                          key=f"scientific_name_{file_name}")
                                with col5:
                                    st.markdown('#####')
                                    st.markdown(f"<h4 style='text-align: center; color: blue;'>Validator</h5>",
                                                unsafe_allow_html=True)
                                    validator_name = annotations_df.loc[
                                        annotations_df['filename_ts'] == file_name, 'validator_name'].values[0]
                                    validator_name_input = st.text_input("*(please, enter your name)*",
                                                                         value=validator_name,
                                                                         key=f"validator_name_{file_name}")
                                with col6:
                                    st.markdown('#####')
                                    st.markdown(f"<h4 style='text-align: center; color: blue;'>Comment</h5>",
                                                unsafe_allow_html=True)
                                    comment = annotations_df.loc[
                                        annotations_df['filename_ts'] == file_name, 'comment'].values[0]
                                    comment_input = st.text_input("*(feel free to tell something)*", value=comment,
                                                                  key=f"validator_comment_{file_name}")
                                annotations.append({
                                    'file_name': file_name,
                                    'group_input': group_input,
                                    'scientific_name_input': scientific_name_input,
                                    'validator_name_input': validator_name_input,
                                    'comment_input': comment_input
                                })
                            submitButton = form.form_submit_button(label="Submit annotations")
                        if submitButton:
                            with st.spinner('Saving annotations...'):
                                for annotation in annotations:
                                    file_name = annotation['file_name']
                                    group_input = annotation['group_input']
                                    scientific_name_input = annotation['scientific_name_input']
                                    validator_name_input = annotation['validator_name_input']
                                    comment_input = annotation['comment_input']
                                    # Update the annotations_df DataFrame with new annotations
                                    annotations_df.loc[
                                        annotations_df['filename_ts'] == file_name, 'validated_class'] = group_input
                                    annotations_df.loc[
                                        annotations_df[
                                            'filename_ts'] == file_name, 'validated_specie'] = scientific_name_input
                                    annotations_df.loc[
                                        annotations_df[
                                            'filename_ts'] == file_name, 'validator_name'] = validator_name_input
                                    annotations_df.loc[
                                        annotations_df['filename_ts'] == file_name, 'comment'] = comment_input
                                annotations_df['validated_class'] = annotations_df['validated_class'].astype(str)

                                # Save to CSV file
                                annotations_df.to_csv(csv_file, index=False)

                                # Update the Google Sheet
                                update_google_sheet(client, rec_name, annotations_df)

                                st.success("All annotations have been saved.")

                                # Remove the analyzed subfolder from the list
                                st.session_state.folders[selected_folder].remove(selected_subfolder)

                                # If no more subfolders in the main folder, remove the main folder as well
                                if not st.session_state.folders[selected_folder]:
                                    del st.session_state.folders[selected_folder]

                                # Mark the folder as available
                                update_annotation_status(selected_folder, "", "available")

                                st.rerun()
                    else:
                        st.error("No audio files found in the selected subfolder.")

        spacing()
    
        # Display the DataFrame
        st.header("Annotated DataFrame")
        st.write(":orange[Feel free to access the dataframe on google sheet through this [link](https://docs.google.com/spreadsheets/d/119CGzxLv0kclMMb3SDYYwrULn2WY77OqDrzR6McEYO0/edit?gid=0#gid=0)]")
        df = get_google_sheet_data(rec_name)
        df_display = df.astype(str)
        st.write(df_display)
        st.markdown('#####')

    if __name__ == "__main__":
        iden()
