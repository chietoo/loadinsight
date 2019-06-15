import logging
import pandas as pd
from generics import task as t
from generics.file_type_enum import SupportedFileReadType


logger = logging.getLogger('LCTK_APPLICATION_LOGGER')


class HeatcoolIndexer(t.Task):
    def __init__(self, name):
        super().__init__(self)
        self.name = name
        self.data_files = [
            { 'name': 'area_loads.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/594.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/596.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/597.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/598.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/833.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/835.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/836.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/837.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/838.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/970.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/971.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/972.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/973.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/974.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/980.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/981.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/982.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/983.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/984.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/985.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/988.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/989.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/990.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/991.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/992.csv', 'read_type': SupportedFileReadType.DATA },
            { 'name': 'noaa/993.csv', 'read_type': SupportedFileReadType.DATA },
        ]
        self.task_function = self._task
        self.output_artifact_enduse_loads = 'enduse_loads.csv'
        
        self.data_map = None
        self.df = None

        # these should be read from config, they are different for RBSA and CEUS
        self.theat = 15
        self.tcool = 25

    def _save_data(self):
        self.save_data(self.df)

    def _get_data(self):
        self.data_map = self.load_data(self.data_files) 
        self.df = self.data_map['area_loads.csv']        

    def _task(self):
        self._get_data()
        logger.info(self.df)

        # output dataframe initialization
        initialization = True

        zipcodes = self.df.zipcode.unique()

        for zipcode in zipcodes:

            zipcode_df = self.df.loc[self.df.zipcode == zipcode]
            zipcode_df = zipcode_df.reset_index()
            
            filename = f'noaa/{str(zipcode)}.csv'
            zipcode_weather = self.data_map[filename]
                
            # validation for date ranges of zip codes load data date range to noaa data for that zipcode
            if (zipcode_df.time.max() > zipcode_weather.DATE.max()) | (zipcode_df.time.min() < zipcode_weather.DATE.min()):
                logger.exception(f'Task {self.name} did not pass validation. Error found in matching noaa weather file date range to {zipcode} zip code.')
                self.did_task_pass_validation = False
                self.on_failure()

            # make start and end dates of weather data match load
            start = zipcode_df.time.min()
            end = zipcode_df.time.max()

            zipcode_weather = zipcode_weather.loc[(zipcode_weather.DATE >= start) & (zipcode_weather.DATE <= end)]

            load_df = pd.DataFrame(columns=['HeatCool','Temperature','Indexer','Heating','Cooling','Ventilation'])

            # apply indexing
            load_df['HeatCool'] = zipcode_df['HeatCool']
            load_df['Temperature'] = zipcode_weather['Temperature']
            load_df['Indexer'] = zipcode_weather.apply(self.temp_dir, axis=1)
            load_df['Heating'] = load_df.apply(self.heat_method, axis=1)
            load_df['Cooling'] = load_df.apply(self.cool_method, axis=1)
            load_df['Ventilation'] = load_df.apply(self.vent_method, axis=1)

            load_df = load_df.fillna(0)

            self.validate(load_df)

            enduses_updated = ['Heating', 'Cooling', 'Ventilation']

            zipcode_df['Ventilation'] = 0 # no ventilation coming in

            # apply changes
            for enduse in enduses_updated:
                zipcode_df[enduse] = zipcode_df[enduse] + load_df[enduse]

            # output dataframe 
            if initialization:
                enduse_loads = zipcode_df
                initialization = False
            else:
                enduse_loads = enduse_loads.append(zipcode_df)

        enduse_loads = enduse_loads.drop('HeatCool', axis=1)
        enduse_loads = enduse_loads.set_index('time')
        enduse_loads = enduse_loads.drop('index', axis=1)

        self.validate(enduse_loads)
        self.save_data({self.output_artifact_enduse_loads: enduse_loads})

    def temp_dir(self, row):
        """
        Function used for seperating heatcool
        """
        if row['Temperature'] < self.theat:
            return "Heating"
        if row['Temperature'] > self.tcool:
            return "Cooling"
        return "Ventilation"

    def heat_method(self, row):
        """
        Function used for seperating heat from heatcool
        """
        if row['Indexer'] == "Heating":
            return row['HeatCool']
        return 0

    def cool_method(self, row):
        """
        Function used for seperating cool from heatcool
        """
        if row['Indexer'] == "Cooling":
            return row['HeatCool']
        return 0

    def vent_method(self, row):
        """
        Function used for seperating vent from heatcool
        """
        if row['Indexer'] == "Ventilation":
            return row['HeatCool']
        return 0

    def validate(self, df):
        """
        Validation
        """
        logger.info(f'Validating task {self.name}')
        if df.isnull().values.any():
            logger.exception(f'Task {self.name} did not pass validation. Error found during grouping of sites to zip codes.')
            self.did_task_pass_validation = False
            self.on_failure()

    def on_failure(self):
        logger.info('Perform task cleanup because we failed')
        super().on_failure()