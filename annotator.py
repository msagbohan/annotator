import streamlit as st
import os
import pandas as pd
import gspread
from google.oauth2 import service_account
import glob
import soundfile as sf
from maad import sound
from maad.util import power2dB
from skimage import transform


@st.cache_resource
def authorize_google_sheets():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    return client


def get_google_sheet_data():
    client = authorize_google_sheets()
    sheet = client.open("XP_final_annotations").worksheet("rec1tes")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return df


@st.cache_data
def load_audio_files(folder):
    audio_files = glob.glob(os.path.join(folder, f"*.WAV"))
    return audio_files


@st.cache_data
def plot_spec(file_path, cmap: str):
    import matplotlib.pyplot as plt
    s, fs = sound.load(file_path)
    Sxx, tn, fn, ext = sound.spectrogram(s, fs, nperseg=1024, noverlap=512, flims=(0, fs // 2))
    Sxx_db = power2dB(Sxx, db_range=70)
    Sxx_db = transform.rescale(Sxx_db, 0.5, anti_aliasing=True, channel_axis=None)
    fig, ax = plt.subplots()
    img = ax.imshow(Sxx_db, aspect='auto', extent=ext, origin='lower', interpolation='bilinear', cmap=cmap)
    fig.colorbar(img, ax=ax, format="%+2.0f dB")
    ax.set(title='Spectrogram', xlabel='Time [s]', ylabel='Frequency [Hz]')
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


def iden():
    # Set up the credentials and client
    st.header("ROIS Clusters Annotator")
    client = authorize_google_sheets()

    # Define a base path input
    col1, col2 = st.columns(2)
    with st.container():
        with col1:
            rec_name = st.selectbox('**:red[Please, select a recorder to analyze]**',
                                    options=['rec1tes', 'rec2dmu', 'rec3dmu', 'rec4dmu', 'rec5dmu', 'rec6dmu'])
        with col2:
            base_path = st.text_input("**:red[Please, enter the path to the folders containing all ROIs Clusters]**",
                                      help='(Example: `/path/to/your/folders` or `C:\\Users\\YourName\\AudioFiles`)',
                                      value='/Volumes/Expansion/xprize/bamscape_birdnet/RESULTS_BIRDNET/32kHz_all_CLUSTERS_COMBINED')

    # Loading the CSV files and Google Sheets
    sheet = client.open("XP_final_annotations").worksheet(f"{rec_name}")
    final_annotations = pd.DataFrame(sheet.get_all_records())
    st.session_state.final_annotations = final_annotations
    annotations_df = st.session_state.final_annotations
    csv_file = f'{rec_name}_all_CLUSTERS_COMBINED.csv'

    # Filter out the annotated rows based on specific columns
    unannotated_df = annotations_df[(annotations_df['validated_class'] == 0) |
                                    (annotations_df['validated_specie'] == 0) |
                                    (annotations_df['validator_name'] == 0)]

    # Load the initial state from the Google Sheet
    if 'folders' not in st.session_state:
        folders = unannotated_df['cluster_number'].astype(str).unique()
        st.session_state.folders = {
            folder: unannotated_df[unannotated_df['cluster_number'] == int(folder)]['period'].astype(
                str).unique().tolist() for folder in folders}

    if base_path:
        # Validate the base path
        if os.path.exists(base_path) and os.path.isdir(base_path):

            col1, col2, col3 = st.columns(3)
            selected_folder = None
            selected_subfolder = None
            with st.container():
                with col1:
                    if st.session_state.folders:
                        selected_folder = st.selectbox("**:red[Select a cluster folder to analyze]**",
                                                       list(st.session_state.folders.keys()))
                    else:
                        st.success(
                            "Congratulations, all the clusters have been annotated! Please select another recorder to annotate.")
                with col2:
                    if selected_folder:
                        subfolders = st.session_state.folders[selected_folder]
                        if subfolders:
                            selected_subfolder = st.selectbox("**:red[Select a subfolder to analyze]**", subfolders)
                with col3:
                    selected_cmap = st.selectbox("**:red[Choose a colormap to display spectrograms]**",
                                                 options=['jet', 'Greys', 'plasma', 'viridis', 'inferno'])

            if selected_folder and selected_subfolder:
                subfolder_path = os.path.join(base_path, selected_folder, selected_subfolder)
                for root, dirs, files in os.walk(subfolder_path, topdown=False):
                    targetfolder = files
                    st.write(targetfolder)
                    st.markdown("---")
                audio_files = load_audio_files(subfolder_path)
                form = st.form(key=f"user_form")
                annotations = []  # Initialize annotations list here
                with form:
                    for i, audio_file in enumerate(audio_files):
                        file_name = os.path.basename(audio_file)
                        cols = [1.70, .8, 1, 1, 1,1]
                        col1, col2, col3, col4, col5, col6 = st.columns(cols)
                        with col1:
                            with st.spinner('Processing...'):
                                st.markdown(f"<h6 style='text-align: center; color: green;'>ROI: {file_name} </h10>",
                                            unsafe_allow_html=True)
                                plot_spec(audio_file, cmap=selected_cmap)
                        with col2:
                            st.markdown(f"<h2 style='text-align: center; color: black;'></h10>", unsafe_allow_html=True)
                            st.markdown('######')
                            audio_data, audio_sr = sf.read(audio_file)
                            st.audio(audio_data, format='audio/wav', sample_rate=audio_sr, )
                        with col3:
                            st.markdown('#####')
                            st.markdown(f"<h4 style='text-align: center; color: blue;'>Group</h5>",
                                        unsafe_allow_html=True)
                            suggested_group = \
                            annotations_df.loc[annotations_df['filename_ts'] == file_name, 'suggested_class'].values[0]
                            group_input = st.text_input("*(feel free to modify)*", value=suggested_group,
                                                        key=f"group_{file_name}")
                        with col4:
                            st.markdown('#####')
                            st.markdown(f"<h4 style='text-align: center; color: blue;'>Species</h5>",
                                        unsafe_allow_html=True)
                            suggested_label = \
                            annotations_df.loc[annotations_df['filename_ts'] == file_name, 'suggested_label'].values[0]
                            scientific_name_input = st.text_input("*(feel free to modify)*", value=suggested_label,
                                                                  key=f"scientific_name_{file_name}")
                        with col5:
                            st.markdown('#####')
                            st.markdown(f"<h4 style='text-align: center; color: blue;'>Validator</h5>",
                                        unsafe_allow_html=True)
                            validator_name = \
                            annotations_df.loc[annotations_df['filename_ts'] == file_name, 'validator_name'].values[0]
                            validator_name_input = st.text_input("*(Please, enter your name)*", value=validator_name,
                                                                 key=f"validator_name_{file_name}")
                        with col6:
                            st.markdown('#####')
                            st.markdown(f"<h4 style='text-align: center; color: blue;'>comment</h5>",
                                        unsafe_allow_html=True)
                            comment = \
                            annotations_df.loc[annotations_df['filename_ts'] == file_name, 'comment'].values[0]
                            comment_input = st.text_input("*(tell us something)*", value=comment,
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
                                annotations_df['filename_ts'] == file_name, 'validated_specie'] = scientific_name_input
                            annotations_df.loc[
                                annotations_df['filename_ts'] == file_name, 'validator_name'] = validator_name_input
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

                        st.experimental_rerun()

                spacing()

                # Display the DataFrame
                st.header("Annotated DataFrame")
                st.write(":orange[Feel free to also access the annotated dataframe on google sheet through this [link](https://docs.google.com/spreadsheets/d/119CGzxLv0kclMMb3SDYYwrULn2WY77OqDrzR6McEYO0/edit?gid=0#gid=0)]")
                df = get_google_sheet_data()
                df_display = df.astype(str)
                st.write(df_display)
                st.markdown('#####')


if __name__ == "__main__":
    iden()
