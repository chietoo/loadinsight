import logging
import pandas as pd
import numpy as np
from generics import task as t
from generics.file_type_enum import SupportedFileReadType


logger = logging.getLogger('LCTK_APPLICATION_LOGGER')


class ZipcodeCorrelation(t.Task):
    def __init__(self, name, pipeline_artifact_dir):
        super().__init__(self)
        self.df = None
        self.name = name
        self.data_map = None
        self.task_function = self._task
        self.pipeline_artifact_dir = pipeline_artifact_dir
        self.input_artifact_projection_locations = 'PROJECTION_LOCATIONS.json'
        self.input_artifact_excluded_locations = 'EXCLUDED_LOCATIONS.json'
        self.input_artifact_full_zipcodes = f'{pipeline_artifact_dir}/full_zipcodes.csv'
        self.output_artifact_correlation_matrix = f'{pipeline_artifact_dir}/correlation_matrix.csv'
        
        # these will be used to generate list of input files
        self.pre_data_files = [ 
            { 'name': self.input_artifact_full_zipcodes, 'read_type': SupportedFileReadType.DATA },
            { 'name': self.input_artifact_projection_locations, 'read_type': SupportedFileReadType.CONFIG },
            { 'name': self.input_artifact_excluded_locations, 'read_type': SupportedFileReadType.CONFIG }
        ]

    def _get_data(self):
        self.pre_data_map = self.load_data(self.pre_data_files) 
        self.full_zipcodes = list(self.pre_data_map[f'{self.pipeline_artifact_dir}/full_zipcodes.csv']['zipcodes'])  
        self.projection_locations = list(self.pre_data_map['PROJECTION_LOCATIONS.json']['cities'].keys())
        self.excluded_locations = self.pre_data_map['EXCLUDED_LOCATIONS.json']['Residential']

        self.data_files = []

        for location in self.full_zipcodes:
            self.data_files.append({ 'name': f'{self.pipeline_artifact_dir}/tmy_base/{str(location)}.csv', 'read_type': SupportedFileReadType.DATA })

        for location in self.projection_locations:
            self.data_files.append({ 'name': f'{self.pipeline_artifact_dir}/tmy_target/{str(location)}.csv', 'read_type': SupportedFileReadType.DATA })

        self.data_map = self.load_data(self.data_files)       

    def _task(self):
        self._get_data()

        correlation_metrics = ['Temperature', 'Solar Zenith Angle', 'GHI', 'DHI', 'DNI', 'Wind Speed', 'Wind Direction', 'Relative Humidity']    
        correlation_matrix = pd.DataFrame(0, index=self.projection_locations, columns=self.full_zipcodes)

        needed_zipcodes = [x for x in self.full_zipcodes if str(x) not in self.excluded_locations['base']]
        needed_zipcodes = [x for x in needed_zipcodes if str(x)[:3] not in self.excluded_locations['base']]
        self.projection_locations = [x for x in self.projection_locations if x not in self.excluded_locations['target']]

        for base in needed_zipcodes:
            for target in self.projection_locations:

                base_filename = f'{self.pipeline_artifact_dir}/tmy_base/{str(base)}.csv'
                target_filename = f'{self.pipeline_artifact_dir}/tmy_target/{str(target)}.csv'

                base_weather = self.data_map[base_filename]
                target_weather = self.data_map[target_filename]

                base_weather = base_weather.set_index(base_weather.columns[0])
                target_weather = target_weather.set_index(target_weather.columns[0])

                if base_weather.shape != target_weather.shape:
                    logger.warning(f'Task {self.name} did not pass validation. TMY weather data sizes do not match for {base} and {target}.')
                    continue

                correlation_vals = []
                for metric in correlation_metrics:       
                    correlation_vals.append(np.ma.corrcoef(base_weather[metric], target_weather[metric])[0][1])

                correlation = sum(correlation_vals) / len(correlation_vals)
                correlation_matrix.ix[target, base] = correlation

        correlation_matrix = self.convert_coef_3digit(correlation_matrix)

        self.validate(correlation_matrix)
        self.on_complete({self.output_artifact_correlation_matrix: correlation_matrix})

    def convert_coef_3digit(self, df):
        """
        Convert correlation of coefficient array from 5 digit zipcodes to 3
        """
        zipcodes_3digit = set()

        for zipcode in self.full_zipcodes:
            zipcodes_3digit.add(str(zipcode)[0:3])

        new_coef = pd.DataFrame(columns=zipcodes_3digit, index=self.projection_locations)

        for city in self.projection_locations:
            row = df.loc[df.index == city].squeeze()
            ordered_row = row.sort_values(ascending=False)

            for index in ordered_row.index:
                cell_val = new_coef.loc[city][str(index)[:3]]

                if cell_val != cell_val:
                    new_coef.at[city,str(index)[:3]] = ordered_row[index]

        new_coef = new_coef.reindex(sorted(new_coef.columns), axis=1)

        return new_coef

    def validate(self, df):
        """
        Validation
        """
        logger.info(f'Validating task {self.name}')
        if df.isnull().values.any():
            logger.exception(f'Task {self.name} did not pass validation. Error found during generating correlation matrix.')
            self.did_task_pass_validation = False
            self.on_failure()

    def on_failure(self):
        logger.info('Perform task cleanup because we failed')
        super().on_failure()
